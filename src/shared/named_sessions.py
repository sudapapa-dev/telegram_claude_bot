"""이름 기반 Claude 세션 관리

사용법:
    manager = NamedSessionManager()

    # 세션 생성
    session = await manager.create("데이빗", "/home/user/project")

    # 메시지 라우팅 (이름 prefix 파싱)
    match = manager.parse_address("데이빗, 리포트 작성해줘")
    # → ("데이빗", "리포트 작성해줘") 또는 None

    # 세션에 질의
    reply = await manager.ask("데이빗", "리포트 작성해줘")

    # 목록 조회
    sessions = manager.list_all()
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.shared.models import NamedSession, NamedSessionStatus

if TYPE_CHECKING:
    from src.shared.database import Database

logger = logging.getLogger(__name__)

# 세션 재시작 알림 콜백 타입: (session_name, error_msg) → Awaitable[None]
RestartCallback = Callable[[str, str], Awaitable[None]]


class NamedSessionNotFoundError(Exception):
    """세션을 찾을 수 없을 때"""


class NamedSessionBusyError(Exception):
    """세션이 사용 중일 때"""


class NamedSessionManager:
    """이름 기반 Claude 세션 관리자.

    세션은 메모리 + DB에 저장하여 봇 재시작 시 복원 가능.
    이름은 대소문자 무시하여 비교.
    각 세션은 자체 영구 ClaudeSession 프로세스를 보유함.
    """

    _MONITOR_INTERVAL: int = 30  # 모니터링 주기 (초)

    def __init__(self, db: Database | None = None) -> None:
        self._db = db
        self._sessions: dict[str, NamedSession] = {}      # normalized_name → NamedSession
        self._processes: dict[str, "ClaudeSession"] = {}  # normalized_name → ClaudeSession
        self._locks: dict[str, asyncio.Lock] = {}         # normalized_name → Lock
        self._default_session: str | None = None          # normalized_name of default session
        self._restart_callbacks: list[RestartCallback] = []
        self._monitor_task: asyncio.Task[None] | None = None

    @staticmethod
    def _normalize(name: str) -> str:
        """이름 정규화 (소문자, 앞뒤 공백 제거)"""
        return name.strip().lower()

    async def _save_to_db(self, session: NamedSession, is_default: bool | None = None) -> None:
        """세션 정보를 DB에 저장 (DB 없으면 무시)"""
        if self._db is None:
            return
        try:
            if is_default is None:
                is_default = self._default_session == session.name
            await self._db.save_named_session(session, is_default=is_default)
        except Exception:
            logger.exception("named session DB 저장 실패 (무시): name=%s", session.display_name)

    async def load_from_db(self) -> int:
        """DB에서 세션 목록을 복원. 복원된 세션 수 반환."""
        if self._db is None:
            return 0
        try:
            rows = await self._db.get_all_named_sessions()
        except Exception:
            logger.exception("named session DB 복원 실패")
            return 0

        count = 0
        for session, is_default in rows:
            key = session.name
            if key in self._sessions:
                continue  # 이미 존재하면 스킵 (기본 세션 등)
            self._sessions[key] = session
            self._locks[key] = asyncio.Lock()
            if is_default:
                self._default_session = key
            count += 1
            logger.info(
                "named session DB 복원: name=%s, uid=%s, dir=%s, default=%s",
                session.display_name, session.session_uid, session.working_dir, is_default,
            )
        if count:
            logger.info("named session DB 복원 완료: %d개", count)
        return count

    async def create(self, display_name: str, working_dir: str | None = None) -> NamedSession:
        """새 이름 세션 생성. 이미 존재하면 ValueError 발생.

        Args:
            display_name: 표시 이름 (원본 대소문자 유지).
            working_dir: 세션의 작업 디렉토리.
                         None이면 data/sessions/{uid}/ 폴더를 자동 생성.
                         uid는 세션 생성 시 부여된 불변 고유 ID.

        Returns:
            생성된 NamedSession 객체.

        Raises:
            ValueError: 같은 이름의 세션이 이미 존재할 때.
        """
        from src.shared.ai_session import _make_working_dir
        if " " in display_name.strip():
            raise ValueError("세션 이름에 공백을 포함할 수 없습니다.")
        key = self._normalize(display_name)
        if key in self._sessions:
            raise ValueError(f"이미 존재하는 세션 이름입니다: '{display_name}'")

        # 신규 세션: uid 먼저 생성 후 폴더 결정
        session_uid = uuid.uuid4().hex[:12]
        if working_dir is None:
            working_dir = _make_working_dir(f"sessions/{session_uid}")

        session = NamedSession(
            name=key,
            display_name=display_name,
            session_uid=session_uid,
            working_dir=working_dir,
        )
        self._sessions[key] = session
        self._locks[key] = asyncio.Lock()
        await self._save_to_db(session)
        logger.info(
            "named session 생성: name=%s, uid=%s, dir=%s",
            display_name, session.session_uid, working_dir,
        )
        return session

    async def _get_or_start_process(self, key: str) -> "ClaudeSession":
        """세션의 ClaudeSession 프로세스를 반환. 없거나 죽어있으면 새로 시작."""
        from src.shared.ai_session import ClaudeSession
        session = self._sessions[key]
        proc = self._processes.get(key)
        if proc is None or not proc.is_alive():
            is_restart = proc is not None and not proc.is_alive()
            proc = ClaudeSession(working_dir=session.working_dir, system_prompt="")
            await proc.start(resume_session_id=session.claude_session_id)
            self._processes[key] = proc
            # 새 프로세스의 session_id 업데이트
            if proc.session_id:
                session.claude_session_id = proc.session_id
            logger.info(
                "named session 프로세스 %s: name=%s, session_id=%s",
                "재시작" if is_restart else "시작",
                session.display_name, session.claude_session_id,
            )
            if is_restart:
                for cb in self._restart_callbacks:
                    try:
                        await cb(session.display_name, session.last_error or "프로세스 종료")
                    except Exception:
                        logger.exception("재시작 콜백 오류: name=%s", session.display_name)
        return proc

    async def _stop_process(self, key: str) -> None:
        """세션 프로세스 종료."""
        proc = self._processes.pop(key, None)
        if proc is not None:
            await proc.stop()

    def get(self, name: str) -> NamedSession | None:
        """이름으로 세션 조회.

        Args:
            name: 세션 이름 (대소문자 무시).

        Returns:
            NamedSession 또는 None (존재하지 않을 경우).
        """
        return self._sessions.get(self._normalize(name))

    def list_all(self) -> list[NamedSession]:
        """모든 세션 목록을 생성 시간 순으로 반환.

        Returns:
            NamedSession 리스트 (생성 시간 오름차순).
        """
        return sorted(self._sessions.values(), key=lambda s: s.created_at)

    async def delete(self, name: str) -> bool:
        """세션 삭제 (프로세스도 종료).

        Args:
            name: 삭제할 세션 이름 (대소문자 무시).

        Returns:
            삭제 성공 시 True, 세션이 없으면 False.
        """
        key = self._normalize(name)
        if key not in self._sessions:
            return False
        await self._stop_process(key)
        del self._sessions[key]
        self._locks.pop(key, None)
        if self._default_session == key:
            self._default_session = None
            logger.info("default session 해제 (세션 삭제로 인해): name=%s", name)
        # DB에서 삭제
        if self._db is not None:
            try:
                await self._db.delete_named_session(key)
            except Exception:
                logger.exception("named session DB 삭제 실패 (무시): name=%s", name)
        logger.info("named session 삭제: name=%s", name)
        return True

    async def reset(self, name: str) -> NamedSession:
        """세션 대화 이력 리셋 (프로세스 재시작, working_dir 유지).

        Args:
            name: 리셋할 세션 이름 (대소문자 무시).

        Returns:
            리셋된 NamedSession 객체.

        Raises:
            NamedSessionNotFoundError: 세션이 존재하지 않을 때.
        """
        key = self._normalize(name)
        session = self._sessions.get(key)
        if not session:
            raise NamedSessionNotFoundError(f"세션을 찾을 수 없습니다: {name}")
        await self._stop_process(key)
        session.claude_session_id = None
        session.message_count = 0
        session.status = NamedSessionStatus.IDLE
        session.last_error = None
        logger.info("named session 리셋: name=%s", name)
        return session

    async def ask(self, name: str, prompt: str, timeout: int = 600) -> str:
        """이름 세션에 질의.

        동일 세션에 대한 동시 요청은 Lock으로 직렬화(순차 처리).
        ClaudeSession 프로세스를 재사용하여 대화 연속성 유지.

        Args:
            name: 대상 세션 이름 (대소문자 무시).
            prompt: Claude에게 전달할 프롬프트.
            timeout: 응답 대기 최대 시간(초). 기본값 600.

        Returns:
            Claude의 응답 텍스트.

        Raises:
            NamedSessionNotFoundError: 세션이 존재하지 않을 때.
            TimeoutError: 응답이 timeout 초 내에 오지 않을 때.
            RuntimeError: Claude Code CLI 실행 실패 시.
        """
        key = self._normalize(name)
        session = self._sessions.get(key)
        if not session:
            raise NamedSessionNotFoundError(f"세션을 찾을 수 없습니다: '{name}'")

        lock = self._locks[key]
        async with lock:
            # Lock 획득 후 세션이 여전히 존재하는지 재확인 (delete와의 race condition 방지)
            session = self._sessions.get(key)
            if not session:
                raise NamedSessionNotFoundError(f"세션을 찾을 수 없습니다: '{name}'")
            session.status = NamedSessionStatus.BUSY
            session.last_used_at = datetime.now(timezone.utc)
            try:
                proc = await self._get_or_start_process(key)
                reply = await proc.ask(prompt, timeout=timeout)
                # session_id 업데이트 (새 프로세스가 생성된 경우 등)
                if proc.session_id:
                    session.claude_session_id = proc.session_id
                session.message_count += 1
                session.last_error = None
                session.status = NamedSessionStatus.IDLE
                await self._save_to_db(session)
                logger.info(
                    "named session ask 완료: name=%s, count=%d",
                    name,
                    session.message_count,
                )
                # elapsed는 ClaudeSession.ask() 내부에서 이미 로깅됨
                return reply
            except asyncio.CancelledError:
                session.status = NamedSessionStatus.IDLE
                raise
            except Exception as e:
                session.last_error = str(e)
                # 프로세스가 죽었을 수 있으므로 제거 → 모니터가 재시작 처리
                await self._stop_process(key)
                session.status = NamedSessionStatus.DEAD
                logger.exception("named session ask 실패 (DEAD): name=%s", name)
                raise

    async def set_default(self, name: str) -> NamedSession:
        """기본 라우팅 세션 설정.

        이후 이름 prefix 없는 메시지는 이 세션으로 전달됨.

        Args:
            name: 기본으로 설정할 세션 이름 (대소문자 무시).

        Returns:
            설정된 NamedSession 객체.

        Raises:
            NamedSessionNotFoundError: 세션이 존재하지 않을 때.
        """
        key = self._normalize(name)
        session = self._sessions.get(key)
        if not session:
            raise NamedSessionNotFoundError(f"세션을 찾을 수 없습니다: '{name}'")
        self._default_session = key
        # DB에 default 플래그 업데이트
        if self._db is not None:
            try:
                await self._db.update_named_session_default(key, True)
            except Exception:
                logger.exception("default session DB 업데이트 실패 (무시)")
        logger.info("default session 설정: name=%s", name)
        return session

    async def clear_default(self) -> None:
        """기본 세션 해제. 이후 이름 없는 메시지는 글로벌 세션 풀로 전달됨."""
        self._default_session = None
        # DB에서 default 플래그 해제
        if self._db is not None:
            try:
                await self._db.clear_named_sessions_default()
            except Exception:
                logger.exception("default session DB 해제 실패 (무시)")
        logger.info("default session 해제")

    @property
    def default_session(self) -> NamedSession | None:
        """현재 설정된 기본 세션. 없으면 None."""
        if self._default_session is None:
            return None
        return self._sessions.get(self._default_session)

    def add_restart_callback(self, cb: RestartCallback) -> None:
        """세션 재시작 알림 콜백 등록.

        DEAD 세션이 재시작될 때 cb(display_name, error_msg)가 호출됨.
        """
        self._restart_callbacks.append(cb)

    async def start_monitor(self) -> None:
        """DEAD 세션 및 죽은 프로세스 모니터링 백그라운드 태스크 시작."""
        if self._monitor_task and not self._monitor_task.done():
            return
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(), name="named-session-monitor"
        )
        logger.info("named session 모니터 시작 (주기=%ds)", self._MONITOR_INTERVAL)

    async def stop_monitor(self) -> None:
        """모니터링 태스크 중지."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        self._monitor_task = None
        logger.info("named session 모니터 중지")

    async def start_all(self) -> None:
        """모든 등록된 세션의 프로세스를 즉시 기동 (봇 시작 시 호출).

        각 세션의 Lock을 획득 후 기동하여 ask()와의 race condition 방지.
        """
        async def _start_one(key: str) -> None:
            lock = self._locks.get(key)
            if lock is None:
                return
            async with lock:
                try:
                    await self._get_or_start_process(key)
                except Exception:
                    session = self._sessions.get(key)
                    name = session.display_name if session else key
                    logger.exception("named session 프로세스 초기 기동 실패: name=%s", name)

        await asyncio.gather(*[_start_one(key) for key in list(self._sessions.keys())])
        logger.info("모든 named session 프로세스 기동 완료 (count=%d)", len(self._sessions))

    async def stop_all(self) -> None:
        """모든 세션 프로세스 종료 (봇 셧다운 시 호출)."""
        keys = list(self._processes.keys())
        for key in keys:
            await self._stop_process(key)
        logger.info("모든 named session 프로세스 종료 완료")

    async def _monitor_loop(self) -> None:
        """주기적으로 DEAD 세션과 죽은 프로세스를 감지하고 처리."""
        while True:
            try:
                await asyncio.sleep(self._MONITOR_INTERVAL)
            except asyncio.CancelledError:
                break
            await self._check_dead_processes()
            await self._revive_dead_sessions()

    async def _check_dead_processes(self) -> None:
        """실행 중이어야 하는데 프로세스가 종료된 세션을 DEAD로 마킹."""
        for key, session in list(self._sessions.items()):
            if session.status == NamedSessionStatus.BUSY:
                continue  # ask() 처리 중 — 건드리지 않음
            proc = self._processes.get(key)
            if proc is not None and not proc.is_alive():
                logger.warning(
                    "named session 프로세스 비정상 종료 감지: name=%s",
                    session.display_name,
                )
                self._processes.pop(key, None)
                if session.status == NamedSessionStatus.IDLE:
                    session.status = NamedSessionStatus.DEAD
                    session.last_error = "프로세스가 예기치 않게 종료됨"

    async def _revive_dead_sessions(self) -> None:
        """DEAD 상태 세션을 재시작 (claude_session_id 초기화 후 IDLE 복원)."""
        dead_sessions = [
            s for s in self._sessions.values()
            if s.status == NamedSessionStatus.DEAD
        ]
        for session in dead_sessions:
            error_msg = session.last_error or "알 수 없는 오류"
            logger.info(
                "named session 재시작: name=%s, error=%s",
                session.display_name, error_msg,
            )
            # 대화 컨텍스트 초기화 후 IDLE 복원 (프로세스는 ask() 때 lazy 시작)
            session.claude_session_id = None
            session.status = NamedSessionStatus.IDLE
            session.last_error = None

            # 등록된 콜백 호출 (텔레그램 알림 등)
            for cb in self._restart_callbacks:
                try:
                    await cb(session.display_name, error_msg)
                except Exception:
                    logger.exception("재시작 콜백 오류: name=%s", session.display_name)

    def parse_address(self, text: str) -> tuple[str, str] | None:
        """텍스트에서 @세션이름 prefix를 파싱.

        형식: "@이름 내용" 또는 "@이름\n내용"
        등록된 세션 이름과 매칭되는 경우만 반환.
        매칭 실패 시 None 반환.

        Args:
            text: 파싱할 입력 텍스트.

        Returns:
            (display_name, content) 튜플, 또는 매칭 실패 시 None.

        예:
            "@지호 안녕" → ("지호", "안녕")
            "@수호 리포트 작성해줘" → ("수호", "리포트 작성해줘")
            "일반 메시지" → None
        """
        m = re.match(r'^@(\S+)\s+(.+)$', text.strip(), re.DOTALL)
        if not m:
            return None

        candidate = m.group(1).strip()
        content = m.group(2).strip()
        if not content:
            return None

        key = self._normalize(candidate)
        if key in self._sessions:
            return (self._sessions[key].display_name, content)

        return None
