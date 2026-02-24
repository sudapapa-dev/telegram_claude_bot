"""AI 세션 관리 - Claude Code CLI 세션 추상화

기본 세션: 단일 ClaudeSession + session_id resume으로 대화 컨텍스트 유지.
시스템 프롬프트(.env)는 기본 세션에만 적용됨.
이름 세션(NamedSession)은 시스템 프롬프트 없이 독립 실행.

작업 디렉토리:
  - 기본 세션:  {data_dir}/default/
  - 이름 세션:  사용자가 /new 또는 /open 시 지정. 미지정 시 {data_dir}/sessions/{uid}/

ClaudeSession 프로세스 모드:
  - stream-json 프로토콜 사용: --input-format stream-json --output-format stream-json
  - 프로세스를 start()로 한 번 기동 후 ask()로 반복 메시지 전송
  - stop()으로 stdin EOF 전달 → 프로세스 자연 종료
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.shared.chat_history import ChatHistoryStore

logger = logging.getLogger(__name__)

# ── 기본 세션 설정 (모듈 레벨 싱글턴) ──
_claude_path: str = "claude"
_model: str | None = None
_data_dir: Path = Path("data")   # 세션 작업 디렉토리 루트
_system_prompt: str = ""
_history_store: "ChatHistoryStore | None" = None
_session_id: str | None = None   # 대화 연속성을 위한 Claude session_id
_lock: asyncio.Lock | None = None  # 기본 세션 직렬화용 Lock
_default_claude_session: "ClaudeSession | None" = None  # 기본 세션 영구 프로세스


def _make_working_dir(subdir: str) -> str:
    """OS별 데이터 디렉토리 아래 서브디렉토리를 생성하고 경로 문자열 반환.

    Windows: %ProgramData%\\Telegram_Claude_Bot\\data\\{subdir}
    Linux/Docker: {_data_dir}/data/{subdir}
    """
    if sys.platform == "win32":
        program_data = os.environ.get("ProgramData", r"C:\ProgramData")
        path = Path(program_data) / "Telegram_Claude_Bot" / "data" / subdir
    else:
        path = _data_dir / "data" / subdir
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def init_default(
    claude_path: str = "claude",
    model: str | None = None,
    data_dir: "Path | str | None" = None,
    system_prompt: str = "",
    **_kwargs,  # 구버전 호환 파라미터 무시 (working_dir 등)
) -> None:
    """기본 세션 설정 초기화. 앱 기동 시 1회 호출."""
    global _claude_path, _model, _data_dir, _system_prompt
    _claude_path = claude_path
    _model = model
    if data_dir is not None:
        _data_dir = Path(data_dir)
    _system_prompt = system_prompt
    logger.info(
        "ai_session 초기화: path=%s, model=%s, data_dir=%s, system_prompt=%s",
        claude_path, model, _data_dir, bool(system_prompt),
    )


def set_history_store(store: "ChatHistoryStore") -> None:
    """대화 이력 스토어 연결"""
    global _history_store
    _history_store = store


def set_system_prompt(prompt: str) -> None:
    """사전 프롬프트 런타임 변경."""
    global _system_prompt
    _system_prompt = prompt
    logger.info("사전 프롬프트 변경됨: %s", bool(prompt))


def get_system_prompt() -> str:
    """현재 사전 프롬프트 반환"""
    return _system_prompt


async def _get_default_claude_session() -> "ClaudeSession":
    """기본 세션의 ClaudeSession 반환. 없거나 죽어있으면 새로 시작."""
    global _default_claude_session
    if _default_claude_session is None or not _default_claude_session.is_alive():
        _default_claude_session = ClaudeSession(
            claude_path=_claude_path,
            model=_model,
            working_dir=_make_working_dir("default"),
            system_prompt=_system_prompt,
        )
        await _default_claude_session.start()
    return _default_claude_session


async def ask(prompt: str, timeout: int = 600, *, save_history: bool = True) -> str:
    """기본 세션에서 Claude에 질의하고 응답 반환.

    단일 Lock으로 직렬화하여 session_id 연속성 유지.
    시스템 프롬프트를 적용함.
    작업 디렉토리: {data_dir}/default/
    """
    async with _get_lock():
        session = await _get_default_claude_session()
        reply = await session.ask(prompt, timeout=timeout)

    if save_history and _history_store is not None:
        sid = session.session_id
        await _history_store.append(role="user", content=prompt, session_id=sid)
        await _history_store.append(role="assistant", content=reply, session_id=sid)

    return reply


async def new_session() -> None:
    """기본 세션 대화 이력 리셋 (프로세스 재시작)"""
    global _default_claude_session
    async with _get_lock():
        if _default_claude_session is not None:
            await _default_claude_session.stop()
            _default_claude_session = None
    logger.info("기본 세션 초기화됨 (프로세스 재시작)")


async def stop() -> None:
    """정리 (프로세스 종료, 앱 종료 시 호출)"""
    global _default_claude_session
    if _default_claude_session is not None:
        await _default_claude_session.stop()
        _default_claude_session = None
    logger.info("ai_session 종료됨")


def get_session_status() -> dict:
    """기본 세션 상태 조회"""
    if _default_claude_session is None:
        return {"has_session": False, "session_id": None}
    sid = _default_claude_session.session_id
    return {
        "has_session": sid is not None,
        "session_id": (sid[:8] + "...") if sid else None,
    }


# ────────────────────────────────────────────────────────────────────────────


class ClaudeSession:
    """영구 Claude Code CLI 세션 (stream-json 프로토콜).

    start()로 프로세스를 기동한 뒤 ask()를 반복 호출해 대화를 이어갈 수 있다.
    stop()으로 stdin을 닫아 프로세스를 자연 종료시킨다.

    사용 패턴:
        session = ClaudeSession(working_dir="...", system_prompt="...")
        await session.start()
        reply1 = await session.ask("안녕?")
        reply2 = await session.ask("다음 질문")
        await session.stop()
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
        self._working_dir = working_dir or _make_working_dir("default")
        self._system_prompt = system_prompt if system_prompt is not None else _system_prompt
        self._proc: asyncio.subprocess.Process | None = None
        self.session_id: str | None = None  # system/init 이벤트에서 받은 session_id

    @property
    def last_session_id(self) -> str | None:
        """하위 호환: session_id 반환"""
        return self.session_id

    def is_alive(self) -> bool:
        """프로세스가 실행 중인지 확인."""
        return self._proc is not None and self._proc.returncode is None

    async def start(self, resume_session_id: str | None = None) -> None:
        """Claude Code CLI 프로세스를 기동.

        Args:
            resume_session_id: 이전 대화를 이어갈 session_id. None이면 새 대화 시작.
        """
        if self.is_alive():
            return

        env = os.environ.copy()
        env.pop("CLAUDECODE", None)  # 중첩 세션 차단 우회
        cwd = str(Path(self._working_dir).resolve()) if self._working_dir else str(Path.cwd())

        cmd: list[str] = [self._claude_path]
        if resume_session_id:
            cmd += ["--resume", resume_session_id]
        cmd += ["--dangerously-skip-permissions"]
        if self._model:
            cmd += ["--model", self._model]
        cmd += [
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
        ]

        logger.info(
            "ClaudeSession 프로세스 시작: model=%s, cwd=%s, resume=%s",
            self._model, cwd, bool(resume_session_id),
        )

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        logger.info("프로세스 기동: pid=%d, cmd=%s", self._proc.pid, " ".join(cmd))

        # session_id는 첫 ask() 응답의 stdout에서 init 이벤트로 수신됨
        # (start 시점에서 blocking 대기하지 않음 — _read_until_result()에서 처리)
        logger.info("ClaudeSession 프로세스 준비 완료: pid=%d", self._proc.pid)

    async def ask(
        self,
        prompt: str,
        timeout: int = 600,
        system_prompt: str | None = None,
        resume_session_id: str | None = None,
    ) -> str:
        """프로세스 stdin에 메시지를 쓰고 result 이벤트까지 읽어 응답 반환.

        프로세스가 살아있지 않으면 start()를 호출 후 진행.
        resume_session_id는 start() 호출 시에만 사용되며 이미 기동된 경우 무시됨.

        Args:
            prompt: Claude에게 전달할 텍스트.
            timeout: 응답 대기 최대 시간(초).
            system_prompt: 프롬프트 앞에 붙일 시스템 프롬프트 (None이면 초기화 값 사용).
            resume_session_id: 프로세스가 없을 때 재시작 시 사용할 이전 session_id.

        Returns:
            Claude의 응답 텍스트.
        """
        if not self.is_alive():
            await self.start(resume_session_id=resume_session_id)

        assert self._proc is not None
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None

        effective_system = system_prompt if system_prompt is not None else self._system_prompt
        if effective_system:
            full_prompt = f"{effective_system}\n\n{prompt}"
        else:
            full_prompt = prompt

        # stream-json stdin 메시지 형식
        message = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": full_prompt}],
            },
            "parent_tool_use_id": None,
        }
        line = json.dumps(message, ensure_ascii=False) + "\n"

        try:
            self._proc.stdin.write(line.encode())
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as e:
            raise RuntimeError(f"Claude 프로세스가 종료됨 (stdin 쓰기 실패): {e}") from e

        import time as _time
        _send_time = _time.monotonic()
        logger.info(
            "Claude 메시지 전송: session_id=%s, prompt_len=%d",
            self.session_id, len(prompt),
        )

        # stdout에서 result 이벤트가 올 때까지 읽기
        try:
            async with asyncio.timeout(timeout):
                result = await self._read_until_result()
            _elapsed = _time.monotonic() - _send_time
            logger.info(
                "Claude 응답 수신: session_id=%s, elapsed=%.1fs, reply_len=%d",
                self.session_id, _elapsed, len(result),
            )
            return result
        except TimeoutError:
            raise TimeoutError(f"Claude 응답 타임아웃 ({timeout}초 초과)")

    async def _read_until_result(self) -> str:
        """stdout NDJSON 스트림을 읽어 result 이벤트의 결과 텍스트를 반환."""
        assert self._proc is not None and self._proc.stdout is not None

        while True:
            line = await self._proc.stdout.readline()
            if not line:
                # 프로세스 종료
                returncode = await self._proc.wait()
                self._proc = None
                # stderr 수집
                stderr_text = ""
                if self._proc is None:
                    pass  # 이미 wait() 완료
                raise RuntimeError(f"Claude 프로세스가 응답 도중 종료됨 (code={returncode})")

            event = _parse_event(line)
            if event is None:
                continue

            event_type = event.get("type", "")

            if event_type == "result":
                # 최종 결과
                result = event.get("result", "")
                if not result:
                    # result가 비어있으면 error 확인
                    if event.get("is_error"):
                        raise RuntimeError(event.get("error", "Claude 오류 발생"))
                return str(result)

            if event_type == "system" and event.get("subtype") == "init":
                # 재시작 후 새 init — session_id 업데이트
                new_sid = event.get("session_id")
                if new_sid:
                    self.session_id = new_sid
                continue

            # assistant / user(tool_result) 이벤트 등은 로그만
            if event_type == "assistant":
                content_blocks = event.get("message", {}).get("content", [])
                for block in content_blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        logger.debug("assistant 스트림: %s…", block["text"][:80])

    async def stop(self) -> None:
        """프로세스를 종료. stdin EOF 전달 후 자연 종료 대기, 실패 시 강제 kill."""
        if self._proc is None:
            return
        proc = self._proc
        self._proc = None

        if proc.returncode is not None:
            return  # 이미 종료됨

        # stdin EOF → Claude 자연 종료 신호
        try:
            if proc.stdin and not proc.stdin.is_closing():
                proc.stdin.close()
                await proc.stdin.wait_closed()
        except Exception:
            pass

        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
            logger.debug("ClaudeSession 프로세스 정상 종료: pid=%d", proc.pid)
        except TimeoutError:
            logger.warning("ClaudeSession 강제 종료: pid=%d", proc.pid)
            proc.kill()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except TimeoutError:
                pass


def _parse_event(line: bytes | str) -> dict | None:
    """NDJSON 한 줄을 파싱해 dict 반환. 실패 시 None."""
    try:
        text = line.decode(errors="replace") if isinstance(line, bytes) else line
        text = text.strip()
        if not text:
            return None
        return json.loads(text)
    except (json.JSONDecodeError, AttributeError):
        return None


def _parse_output(raw: str) -> tuple[str, str | None]:
    """Claude Code JSON 출력에서 (결과 텍스트, session_id) 추출 (레거시 호환)"""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            session_id: str | None = data.get("session_id") or None
            if "result" in data:
                return str(data["result"]), session_id
            if "content" in data:
                texts = [
                    b["text"]
                    for b in data["content"]
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                if texts:
                    return "\n".join(texts), session_id
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return raw, None
