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

from src.shared.models import AIEngine, NamedSession, NamedSessionStatus

if TYPE_CHECKING:
    from src.shared.ai_session import ClaudeSession, CodexSession, GeminiSession
    from src.shared.database import Database

logger = logging.getLogger(__name__)

# 세션 재시작 알림 콜백 타입: (session_name, error_msg) → Awaitable[None]
RestartCallback = Callable[[str, str], Awaitable[None]]


class NamedSessionNotFoundError(Exception):
    """세션을 찾을 수 없을 때"""


class NamedSessionBusyError(Exception):
    """세션이 사용 중일 때"""


class AmbiguousSessionError(Exception):
    """같은 이름의 세션이 여러 엔진에 존재하여 특정할 수 없을 때"""

    def __init__(self, name: str, engines: list[str]) -> None:
        self.name = name
        self.engines = engines
        prefix_hint = " / ".join(
            {"claude": "@", "gemini": "@@", "codex": "@@@"}.get(e, e) + name
            for e in engines
        )
        super().__init__(
            f"'{name}' 세션이 여러 엔진에 존재합니다 ({', '.join(engines)}).\n"
            f"엔진 prefix를 지정하세요: {prefix_hint}"
        )


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
        self._processes: dict[str, "ClaudeSession | GeminiSession | CodexSession"] = {}  # key → AI session
        self._locks: dict[str, asyncio.Lock] = {}         # normalized_name → Lock
        self._default_session: str | None = None          # normalized_name of default session
        self._restart_callbacks: list[RestartCallback] = []
        self._monitor_task: asyncio.Task[None] | None = None

    # 메시지 prefix → 엔진 매핑 (@=Claude, @@=Gemini, @@@=GPT)
    PREFIX_ENGINE_MAP: dict[str, AIEngine] = {
        "@": AIEngine.CLAUDE,
        "@@": AIEngine.GEMINI,
        "@@@": AIEngine.CODEX,
    }

    # 엔진 → 아이콘 매핑
    ENGINE_ICONS: dict[AIEngine, str] = {
        AIEngine.CLAUDE: "🟣",
        AIEngine.GEMINI: "💎",
        AIEngine.CODEX: "🤖",
    }

    @staticmethod
    def _normalize(name: str) -> str:
        """이름 정규화 (소문자, 앞뒤 공백 제거)"""
        return name.strip().lower()

    @staticmethod
    def _make_key(engine: AIEngine, name: str) -> str:
        """엔진+이름으로 고유 세션 키 생성."""
        return f"{engine.value}:{name.strip().lower()}"

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
            # DB에서 복원: name 필드가 이미 engine:name 형식이면 그대로 사용
            key = session.name
            if ":" not in key:
                # 레거시 데이터: engine prefix 없음 → claude로 마이그레이션
                key = self._make_key(session.engine, session.display_name)
                session.name = key
            if key in self._sessions:
                continue  # 이미 존재하면 스킵 (기본 세션 등)
            self._sessions[key] = session
            self._locks[key] = asyncio.Lock()
            if is_default:
                self._default_session = key
            count += 1
            logger.info(
                "named session DB 복원: engine=%s, name=%s, uid=%s, dir=%s, default=%s",
                session.engine.value, session.display_name, session.session_uid,
                session.working_dir, is_default,
            )
        if count:
            logger.info("named session DB 복원 완료: %d개", count)
        return count

    async def create(
        self,
        display_name: str,
        working_dir: str | None = None,
        engine: AIEngine = AIEngine.CLAUDE,
    ) -> NamedSession:
        """새 이름 세션 생성. 이미 존재하면 ValueError 발생.

        Args:
            display_name: 표시 이름 (원본 대소문자 유지).
            working_dir: 세션의 작업 디렉토리.
                         None이면 data/sessions/{uid}/ 폴더를 자동 생성.
            engine: AI 엔진 타입 (claude/gemini/codex).

        Returns:
            생성된 NamedSession 객체.

        Raises:
            ValueError: 같은 엔진+이름의 세션이 이미 존재할 때.
        """
        from src.shared.ai_session import _make_working_dir
        if " " in display_name.strip():
            raise ValueError("세션 이름에 공백을 포함할 수 없습니다.")
        key = self._make_key(engine, display_name)
        if key in self._sessions:
            raise ValueError(f"이미 존재하는 세션입니다: [{engine.value}] '{display_name}'")

        # 신규 세션: uid 먼저 생성 후 폴더 결정
        session_uid = uuid.uuid4().hex[:12]
        if working_dir is None:
            working_dir = _make_working_dir(f"sessions/{session_uid}")

        session = NamedSession(
            name=key,
            display_name=display_name,
            engine=engine,
            session_uid=session_uid,
            working_dir=working_dir,
        )
        self._sessions[key] = session
        self._locks[key] = asyncio.Lock()
        await self._save_to_db(session)
        logger.info(
            "named session 생성: engine=%s, name=%s, uid=%s, dir=%s",
            engine.value, display_name, session.session_uid, working_dir,
        )
        return session

    def _create_session_for_engine(self, session: NamedSession) -> "ClaudeSession | GeminiSession | CodexSession":
        """엔진 타입에 따라 적절한 CLI 세션 객체 생성."""
        if session.engine == AIEngine.GEMINI:
            from src.shared.ai_session import GeminiSession
            return GeminiSession(working_dir=session.working_dir, system_prompt="")
        elif session.engine == AIEngine.CODEX:
            from src.shared.ai_session import CodexSession
            return CodexSession(working_dir=session.working_dir, system_prompt="")
        else:
            from src.shared.ai_session import ClaudeSession
            return ClaudeSession(working_dir=session.working_dir, system_prompt="")

    async def _get_or_start_process(self, key: str) -> "ClaudeSession | GeminiSession | CodexSession":
        """세션의 CLI 프로세스를 반환. 없거나 죽어있으면 새로 시작."""
        session = self._sessions[key]
        proc = self._processes.get(key)
        if proc is None or not proc.is_alive():
            is_restart = proc is not None and not proc.is_alive()
            proc = self._create_session_for_engine(session)
            await proc.start(resume_session_id=session.claude_session_id)
            self._processes[key] = proc
            # 새 프로세스의 session_id 업데이트
            if proc.session_id:
                session.claude_session_id = proc.session_id
            logger.info(
                "named session 프로세스 %s: engine=%s, name=%s, session_id=%s",
                "재시작" if is_restart else "시작",
                session.engine.value, session.display_name, session.claude_session_id,
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

    def _find_key(self, name: str, engine: AIEngine | None = None) -> str | None:
        """이름(및 선택적 엔진)으로 세션 키를 찾음.

        engine이 지정되면 정확히 매칭.
        미지정 시 이름이 일치하는 세션을 검색하되, 여러 엔진에 동일 이름이 존재하면
        AmbiguousSessionError를 발생시킴.
        """
        if engine is not None:
            key = self._make_key(engine, name)
            return key if key in self._sessions else None

        # engine 미지정: 이름으로 검색
        norm = self._normalize(name)
        # 레거시 키 (engine prefix 없는 구형 데이터) 먼저 확인
        if norm in self._sessions:
            return norm
        matches = [
            key for key, session in self._sessions.items()
            if self._normalize(session.display_name) == norm
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            engines = [self._sessions[k].engine.value for k in matches]
            raise AmbiguousSessionError(name, engines)
        return None

    def parse_name_engine(self, text: str) -> tuple[str, AIEngine | None]:
        """'@name', '@@name', '@@@name' 형식에서 (clean_name, engine) 추출.

        prefix가 없으면 engine=None 반환.
        """
        m = re.match(r'^(@{1,3})([^@\s].*)$', text.strip())
        if m:
            prefix = m.group(1)
            name = m.group(2).strip()
            engine = self.PREFIX_ENGINE_MAP.get(prefix)
            return name, engine
        return text.strip(), None

    def get(self, name: str, engine: AIEngine | None = None) -> NamedSession | None:
        """이름으로 세션 조회.

        Args:
            name: 세션 이름 (대소문자 무시).
            engine: AI 엔진 타입 (None이면 이름만으로 검색).

        Returns:
            NamedSession 또는 None (존재하지 않을 경우).
        """
        key = self._find_key(name, engine)
        return self._sessions.get(key) if key else None

    def list_all(self) -> list[NamedSession]:
        """모든 세션 목록을 생성 시간 순으로 반환.

        Returns:
            NamedSession 리스트 (생성 시간 오름차순).
        """
        return sorted(self._sessions.values(), key=lambda s: s.created_at)

    async def delete_all(self) -> int:
        """모든 세션을 삭제 (프로세스 종료 + DB 삭제).

        Returns:
            삭제된 세션 수.
        """
        keys = list(self._sessions.keys())
        count = 0
        for key in keys:
            await self._stop_process(key)
            session = self._sessions.pop(key, None)
            self._locks.pop(key, None)
            if session and self._db is not None:
                try:
                    await self._db.delete_named_session(key)
                except Exception:
                    logger.exception("세션 DB 삭제 실패 (무시): key=%s", key)
            count += 1
        self._default_session = None
        if self._db is not None:
            try:
                await self._db.clear_named_sessions_default()
            except Exception:
                pass
        logger.info("모든 named session 삭제: %d개", count)
        return count

    async def delete(self, name: str, engine: AIEngine | None = None) -> bool:
        """세션 삭제 (프로세스도 종료).

        Args:
            name: 삭제할 세션 이름 (대소문자 무시).
            engine: AI 엔진 타입 (None이면 이름만으로 검색).

        Returns:
            삭제 성공 시 True, 세션이 없으면 False.
        """
        key = self._find_key(name, engine)
        if not key or key not in self._sessions:
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

    async def delete_all_by_name(self, name: str) -> int:
        """주어진 표시 이름을 가진 모든 엔진 세션 삭제.

        Returns:
            삭제된 세션 수.
        """
        norm = self._normalize(name)
        matching_keys = [
            key for key, session in self._sessions.items()
            if self._normalize(session.display_name) == norm
        ]
        count = 0
        for key in matching_keys:
            await self._stop_process(key)
            session = self._sessions.pop(key, None)
            self._locks.pop(key, None)
            if key == self._default_session:
                self._default_session = None
            if session and self._db is not None:
                try:
                    await self._db.delete_named_session(key)
                except Exception:
                    logger.exception("세션 DB 삭제 실패 (무시): key=%s", key)
            count += 1
        logger.info("named session 이름별 삭제: name=%s, count=%d", name, count)
        return count

    async def delete_by_engine(self, engine: AIEngine) -> int:
        """특정 엔진의 모든 세션 삭제.

        Returns:
            삭제된 세션 수.
        """
        matching_keys = [
            key for key, session in self._sessions.items()
            if session.engine == engine
        ]
        count = 0
        for key in matching_keys:
            await self._stop_process(key)
            session = self._sessions.pop(key, None)
            self._locks.pop(key, None)
            if key == self._default_session:
                self._default_session = None
            if session and self._db is not None:
                try:
                    await self._db.delete_named_session(key)
                except Exception:
                    logger.exception("세션 DB 삭제 실패 (무시): key=%s", key)
            count += 1
        logger.info("named session 엔진별 삭제: engine=%s, count=%d", engine.value, count)
        return count

    async def reset(self, name: str, engine: AIEngine | None = None) -> NamedSession:
        """세션 대화 이력 리셋 (프로세스 재시작, working_dir 유지).

        Args:
            name: 리셋할 세션 이름 (대소문자 무시).
            engine: AI 엔진 타입 (None이면 이름만으로 검색).

        Returns:
            리셋된 NamedSession 객체.

        Raises:
            NamedSessionNotFoundError: 세션이 존재하지 않을 때.
        """
        key = self._find_key(name, engine)
        session = self._sessions.get(key) if key else None
        if not session:
            raise NamedSessionNotFoundError(f"세션을 찾을 수 없습니다: {name}")
        await self._stop_process(key)
        session.claude_session_id = None
        session.message_count = 0
        session.status = NamedSessionStatus.IDLE
        session.last_error = None
        logger.info("named session 리셋: name=%s", name)
        return session

    async def ask(self, name: str, prompt: str, timeout: int = 1200, engine: AIEngine | None = None) -> str:
        """이름 세션에 질의.

        동일 세션에 대한 동시 요청은 Lock으로 직렬화(순차 처리).
        CLI 프로세스를 재사용하여 대화 연속성 유지.

        Args:
            name: 대상 세션 이름 (대소문자 무시).
            prompt: AI에게 전달할 프롬프트.
            timeout: 응답 대기 최대 시간(초). 기본값 1200 (20분).
            engine: AI 엔진 타입 (None이면 이름만으로 검색).

        Returns:
            AI의 응답 텍스트.

        Raises:
            NamedSessionNotFoundError: 세션이 존재하지 않을 때.
            TimeoutError: 응답이 timeout 초 내에 오지 않을 때.
            RuntimeError: CLI 실행 실패 시.
        """
        key = self._find_key(name, engine)
        session = self._sessions.get(key) if key else None
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
                return reply
            except asyncio.CancelledError:
                session.status = NamedSessionStatus.IDLE
                raise
            except TimeoutError:
                # 타임아웃: 프로세스는 살려두고 IDLE로 복원 (다음 요청에서 재사용)
                session.status = NamedSessionStatus.IDLE
                logger.warning("named session ask 타임아웃: name=%s, timeout=%ds", name, timeout)
                raise
            except Exception as e:
                session.last_error = str(e)
                # 프로세스가 죽었을 수 있으므로 제거 → 모니터가 재시작 처리
                await self._stop_process(key)
                session.status = NamedSessionStatus.DEAD
                logger.exception("named session ask 실패 (DEAD): name=%s", name)
                raise

    async def set_default(self, name: str, engine: AIEngine | None = None) -> NamedSession:
        """기본 라우팅 세션 설정.

        이후 이름 prefix 없는 메시지는 이 세션으로 전달됨.

        Args:
            name: 기본으로 설정할 세션 이름 (대소문자 무시).
            engine: AI 엔진 타입 (None이면 이름만으로 검색).

        Returns:
            설정된 NamedSession 객체.

        Raises:
            NamedSessionNotFoundError: 세션이 존재하지 않을 때.
        """
        key = self._find_key(name, engine)
        session = self._sessions.get(key) if key else None
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
        """모든 등록된 Claude 세션의 프로세스를 즉시 기동 (봇 시작 시 호출).

        Gemini/Codex는 단발 실행이므로 미리 기동하지 않음.
        각 세션의 Lock을 획득 후 기동하여 ask()와의 race condition 방지.
        """
        async def _start_one(key: str) -> None:
            session = self._sessions.get(key)
            if session and session.engine != AIEngine.CLAUDE:
                return  # 단발 실행 엔진은 미리 기동하지 않음
            lock = self._locks.get(key)
            if lock is None:
                return
            async with lock:
                try:
                    await self._get_or_start_process(key)
                except Exception:
                    name = session.display_name if session else key
                    logger.exception("named session 프로세스 초기 기동 실패: name=%s", name)

        await asyncio.gather(*[_start_one(key) for key in list(self._sessions.keys())])
        claude_count = sum(1 for s in self._sessions.values() if s.engine == AIEngine.CLAUDE)
        logger.info("Claude named session 프로세스 기동 완료 (count=%d/%d)", claude_count, len(self._sessions))

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
        """DEAD 상태 세션을 재시작 후 IDLE 복원.

        Claude: 대화 컨텍스트 초기화 (claude_session_id=None → 새 대화 시작).
        Gemini/Codex: session_id 보존 (단발 실행 방식이므로 컨텍스트 유지 가능).
        """
        dead_sessions = [
            s for s in self._sessions.values()
            if s.status == NamedSessionStatus.DEAD
        ]
        for session in dead_sessions:
            error_msg = session.last_error or "알 수 없는 오류"
            logger.info(
                "named session 재시작: engine=%s, name=%s, error=%s",
                session.engine.value, session.display_name, error_msg,
            )
            # Claude만 세션 초기화 (영구 프로세스 재시작 → 새 대화)
            # Gemini/Codex는 단발 실행이므로 session_id를 보존해 대화 연속성 유지
            if session.engine == AIEngine.CLAUDE:
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
        """텍스트에서 prefix+세션이름을 파싱.

        형식: "@이름 내용" (Claude), "@@이름 내용" (Gemini), "@@@이름 내용" (GPT)
        등록된 세션 이름과 매칭되는 경우만 반환.
        매칭 실패 시 None 반환.

        Args:
            text: 파싱할 입력 텍스트.

        Returns:
            (session_key, content) 튜플, 또는 매칭 실패 시 None.
            session_key는 내부 키 (engine:name 형식).

        예:
            "@지호 안녕" → Claude '지호' 세션
            "@@수호 리포트" → Gemini '수호' 세션
            "@@@데이빗 코드 작성" → GPT '데이빗' 세션
        """
        m = re.match(r'^(@{1,3})([^@\s]\S*)\s+(.+)$', text.strip(), re.DOTALL)
        if not m:
            return None

        prefix = m.group(1)
        candidate = m.group(2).strip()
        content = m.group(3).strip()
        if not content:
            return None

        engine = self.PREFIX_ENGINE_MAP.get(prefix)
        if engine is None:
            return None

        key = self._make_key(engine, candidate)
        if key in self._sessions:
            return (self._sessions[key].display_name, content)

        return None

    def parse_address_full(self, text: str) -> tuple[str, str, AIEngine] | None:
        """parse_address 확장 버전 — 엔진 정보도 함께 반환.

        Returns:
            (display_name, content, engine) 튜플, 또는 매칭 실패 시 None.
        """
        m = re.match(r'^(@{1,3})([^@\s]\S*)\s+(.+)$', text.strip(), re.DOTALL)
        if not m:
            return None

        prefix = m.group(1)
        candidate = m.group(2).strip()
        content = m.group(3).strip()
        if not content:
            return None

        engine = self.PREFIX_ENGINE_MAP.get(prefix)
        if engine is None:
            return None

        key = self._make_key(engine, candidate)
        if key in self._sessions:
            return (self._sessions[key].display_name, content, engine)

        return None

    def list_by_engine(self, engine: AIEngine | None = None) -> list[NamedSession]:
        """엔진 타입별 세션 목록. None이면 전체."""
        sessions = sorted(self._sessions.values(), key=lambda s: s.created_at)
        if engine is not None:
            return [s for s in sessions if s.engine == engine]
        return sessions
