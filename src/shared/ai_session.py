"""AI 세션 관리 - Claude Code CLI 세션 추상화

기본(default) 세션 풀: 봇 전체에서 공유하는 세션 풀.
  - idle 세션이 있으면 재사용, 없으면 새로 생성.
  - 컨텍스트(대화 이력)는 단일 공유 (현재와 동일).
독립(ClaudeSession) 세션: /task 명령처럼 격리된 독립 작업용 세션.
"""
from __future__ import annotations

import asyncio
import logging
import os
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.shared.chat_history import ChatHistoryStore

logger = logging.getLogger(__name__)

# ── 기본 세션 설정 (모듈 레벨 싱글턴) ──
_claude_path: str = "claude"
_model: str | None = None
_working_dir: str | None = None
_scripts_dir: str | None = None
_system_prompt: str = ""
_history_store: "ChatHistoryStore | None" = None
_pool: "SessionPool | None" = None
_pool_size: int = 3


def init_default(
    claude_path: str = "claude",
    model: str | None = None,
    working_dir: str | None = None,
    scripts_dir: str | None = None,
    pool_size: int = 3,
    system_prompt: str = "",
) -> None:
    """기본 세션 설정 초기화. 앱 기동 시 1회 호출."""
    global _claude_path, _model, _working_dir, _scripts_dir, _pool_size, _system_prompt
    _claude_path = claude_path
    _model = model
    _working_dir = working_dir
    _scripts_dir = scripts_dir
    _pool_size = pool_size
    _system_prompt = system_prompt
    logger.info(
        "ai_session 초기화: path=%s, model=%s, cwd=%s, pool_size=%d, system_prompt=%s",
        claude_path, model, working_dir, pool_size, bool(system_prompt),
    )


def set_history_store(store: "ChatHistoryStore") -> None:
    """대화 이력 스토어 연결"""
    global _history_store
    _history_store = store


def _get_pool() -> "SessionPool":
    """기본 세션 풀 반환 (없으면 생성)"""
    global _pool
    if _pool is None:
        _pool = SessionPool(
            max_size=_pool_size,
            claude_path=_claude_path,
            model=_model,
            working_dir=_working_dir,
            system_prompt=_system_prompt,
        )
    return _pool


def set_system_prompt(prompt: str) -> None:
    """사전 프롬프트 런타임 변경. 변경 후 새 요청부터 적용."""
    global _system_prompt, _pool
    _system_prompt = prompt
    if _pool is not None:
        _pool.set_system_prompt(prompt)
    logger.info("사전 프롬프트 변경됨: %s", bool(prompt))


def get_system_prompt() -> str:
    """현재 사전 프롬프트 반환"""
    return _system_prompt


async def ask(prompt: str, timeout: int = 600) -> str:
    """기본 세션 풀에서 idle 세션을 얻어 Claude에 질의하고 응답 반환"""
    pool = _get_pool()
    reply = await pool.ask(prompt, timeout=timeout)

    # 대화 이력 저장
    if _history_store is not None:
        await _history_store.append(role="user", content=prompt)
        await _history_store.append(role="assistant", content=reply)

    return reply


async def new_session() -> None:
    """기본 세션 풀 초기화 - 모든 세션 종료 후 재생성"""
    global _pool
    if _pool is not None:
        await _pool.shutdown()
        _pool = None
    logger.info("기본 세션 풀 초기화됨")


async def stop() -> None:
    """기본 세션 풀 종료 (앱 종료 시 호출)"""
    global _pool
    if _pool is not None:
        await _pool.shutdown()
        _pool = None
    logger.info("ai_session 종료됨")


def get_pool_status() -> dict:
    """세션 풀 상태 조회 (bot_data 등 외부 노출용)"""
    if _pool is None:
        return {"pool_size": _pool_size, "idle": 0, "busy": 0, "total": 0}
    return _pool.status()


def get_active_sessions() -> list[dict]:
    """현재 BUSY 세션의 상태 목록 반환 (모니터링용)
    각 항목: {idx, pid, msg_id, alive}
    """
    if _pool is None:
        return []
    return _pool.active_sessions()


# ────────────────────────────────────────────────────────────────────────────


class _SessionState(Enum):
    IDLE = auto()
    BUSY = auto()


class SessionPool:
    """ClaudeSession 풀.

    idle 세션을 재사용하고, 모두 바쁘면 풀 최대 크기까지 새 세션을 생성.
    max_size 초과 요청은 큐에서 대기.
    컨텍스트는 공유하지 않음 (각 세션은 stateless, claude -p 1회 실행).
    """

    def __init__(
        self,
        max_size: int,
        claude_path: str,
        model: str | None,
        working_dir: str | None,
        system_prompt: str = "",
    ) -> None:
        self._max_size = max_size
        self._claude_path = claude_path
        self._model = model
        self._working_dir = working_dir
        self._system_prompt = system_prompt
        self._sessions: list[ClaudeSession] = []
        self._states: list[_SessionState] = []
        self._lock = asyncio.Lock()
        self._available = asyncio.Semaphore(max_size)

    def set_system_prompt(self, prompt: str) -> None:
        """사전 프롬프트 런타임 변경"""
        self._system_prompt = prompt

    def status(self) -> dict:
        busy = sum(1 for s in self._states if s == _SessionState.BUSY)
        return {
            "pool_size": self._max_size,
            "total": len(self._sessions),
            "idle": len(self._sessions) - busy,
            "busy": busy,
        }

    def active_sessions(self) -> list[dict]:
        """현재 BUSY 세션의 상태 목록 반환 (모니터링용)"""
        result = []
        for i, (session, state) in enumerate(zip(self._sessions, self._states)):
            if state == _SessionState.BUSY:
                result.append({
                    "idx": i,
                    "pid": session.pid,
                    "msg_id": session.current_msg_id,
                    "alive": session.is_process_alive(),
                })
        return result

    async def ask(self, prompt: str, timeout: int = 600) -> str:
        """idle 세션을 획득하여 질의하고 반환 후 idle로 복원"""
        await self._available.acquire()
        session, idx = await self._acquire_session()
        try:
            return await session.ask(prompt, timeout=timeout, system_prompt=self._system_prompt)
        finally:
            await self._release_session(idx)
            self._available.release()

    async def _acquire_session(self) -> tuple[ClaudeSession, int]:
        """idle 세션 반환. 없으면 새로 생성 (max_size 이내)."""
        async with self._lock:
            # idle 세션 검색
            for i, state in enumerate(self._states):
                if state == _SessionState.IDLE:
                    self._states[i] = _SessionState.BUSY
                    logger.debug("세션 재사용: idx=%d", i)
                    return self._sessions[i], i

            # idle 없음 → 새 세션 생성
            session = ClaudeSession(
                claude_path=self._claude_path,
                model=self._model,
                working_dir=self._working_dir,
                system_prompt=self._system_prompt,
            )
            await session.start()
            idx = len(self._sessions)
            self._sessions.append(session)
            self._states.append(_SessionState.BUSY)
            logger.info("새 세션 생성: idx=%d, pool_total=%d/%d", idx, len(self._sessions), self._max_size)
            return session, idx

    async def _release_session(self, idx: int) -> None:
        async with self._lock:
            if idx < len(self._states):
                self._states[idx] = _SessionState.IDLE
                logger.debug("세션 반환: idx=%d", idx)

    async def shutdown(self) -> None:
        """모든 세션 종료"""
        async with self._lock:
            for session in self._sessions:
                await session.stop()
            self._sessions.clear()
            self._states.clear()
        logger.info("세션 풀 종료됨")


# ────────────────────────────────────────────────────────────────────────────


class ClaudeSession:
    """독립 Claude Code CLI 세션.

    /task 명령 등 격리된 1회성 작업에 사용.
    start() → ask() → stop() 순서로 사용.
    """

    def __init__(
        self,
        claude_path: str | None = None,
        model: str | None = None,
        working_dir: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._claude_path = claude_path or _claude_path
        self._model = model or _model
        self._working_dir = working_dir or _working_dir
        self._system_prompt = system_prompt if system_prompt is not None else _system_prompt
        self._started = False
        self._proc: asyncio.subprocess.Process | None = None  # 실행 중인 프로세스
        self._current_msg_id: str | None = None               # 처리 중인 msg_queue_id

    async def start(self) -> None:
        """세션 준비 (현재는 상태 플래그만 설정)"""
        self._started = True
        logger.debug("ClaudeSession 시작")

    @property
    def pid(self) -> int | None:
        """현재 실행 중인 Claude 프로세스 PID. 실행 중이 아니면 None."""
        return self._proc.pid if self._proc is not None else None

    @property
    def current_msg_id(self) -> str | None:
        """현재 처리 중인 msg_queue_id"""
        return self._current_msg_id

    def is_process_alive(self) -> bool:
        """Claude 프로세스가 실행 중인지 확인"""
        if self._proc is None:
            return False
        return self._proc.returncode is None  # None이면 아직 실행 중

    async def ask(self, prompt: str, timeout: int = 600, system_prompt: str | None = None, msg_id: str | None = None) -> str:
        """Claude Code CLI를 1회 실행하여 응답 반환"""
        if not self._started:
            await self.start()

        env = os.environ.copy()
        cwd = self._working_dir or str(Path.cwd())

        # 사전 프롬프트 적용 (ask() 인자 > 인스턴스 설정 순)
        effective_system = system_prompt if system_prompt is not None else self._system_prompt
        if effective_system:
            full_prompt = f"{effective_system}\n\n{prompt}"
        else:
            full_prompt = prompt

        cmd: list[str] = [self._claude_path, "-p", full_prompt]
        if self._model:
            cmd += ["--model", self._model]
        cmd += ["--output-format", "json"]

        self._current_msg_id = msg_id
        logger.info(
            "Claude Code 실행: model=%s, cwd=%s, prompt_len=%d, msg_id=%s",
            self._model, cwd, len(prompt), msg_id,
        )

        returncode: int | None = None
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            logger.debug("프로세스 시작: pid=%d, msg_id=%s", self._proc.pid, msg_id)
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                self._proc.communicate(), timeout=timeout
            )
            returncode = self._proc.returncode
        except asyncio.TimeoutError:
            if self._proc and self._proc.returncode is None:
                self._proc.kill()
            raise TimeoutError(f"Claude 응답 타임아웃 ({timeout}초 초과)")
        except FileNotFoundError:
            raise RuntimeError(
                f"Claude Code CLI를 찾을 수 없습니다: '{self._claude_path}'. "
                "설치 여부 및 PATH를 확인하세요."
            )
        finally:
            self._proc = None
            self._current_msg_id = None

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")

        if returncode != 0:
            err_msg = stderr.strip() or f"종료 코드: {returncode}"
            logger.error("Claude Code 오류: %s", err_msg[:500])
            raise RuntimeError(err_msg)

        return _parse_output(stdout)

    async def stop(self) -> None:
        """세션 종료. 실행 중인 프로세스가 있으면 종료."""
        if self._proc is not None and self._proc.returncode is None:
            logger.info("프로세스 강제 종료: pid=%d, msg_id=%s", self._proc.pid, self._current_msg_id)
            self._proc.kill()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
            self._proc = None
            self._current_msg_id = None
        self._started = False
        logger.debug("ClaudeSession 종료")


def _parse_output(raw: str) -> str:
    """Claude Code JSON 출력에서 결과 텍스트 추출"""
    import json

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            if "result" in data:
                return str(data["result"])
            if "content" in data:
                texts = [
                    b["text"]
                    for b in data["content"]
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                if texts:
                    return "\n".join(texts)
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return raw
