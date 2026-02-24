from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

from src.shared.models import ChatMessage, NamedSession, NamedSessionStatus

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_history (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    session_name TEXT,
    session_uid TEXT,
    session_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS named_sessions (
    name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    session_uid TEXT NOT NULL,
    working_dir TEXT NOT NULL,
    claude_session_id TEXT,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0
);
"""


def _require_db(db: aiosqlite.Connection | None) -> aiosqlite.Connection:
    """DB 초기화 여부를 검사하고 연결 객체를 반환"""
    if db is None:
        raise RuntimeError("DB가 초기화되지 않았습니다. initialize()를 먼저 호출하세요.")
    return db


class Database:
    """SQLite 비동기 데이터베이스"""

    def __init__(self, db_path: str) -> None:
        self._path = str(Path(db_path).resolve())
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """DB 연결 및 스키마 초기화"""
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._migrate(self._db)
        await self._db.commit()
        logger.info("DB 초기화 완료: %s", self._path)

    @staticmethod
    async def _migrate(db: aiosqlite.Connection) -> None:
        """기존 DB에 누락된 컬럼 추가 (무중단 마이그레이션)"""
        async with db.execute("PRAGMA table_info(chat_history)") as cur:
            columns = {row["name"] for row in await cur.fetchall()}
        for col in ("session_name", "session_uid", "session_id"):
            if col not in columns:
                await db.execute(f"ALTER TABLE chat_history ADD COLUMN {col} TEXT")
                logger.info("chat_history 마이그레이션: %s 컬럼 추가", col)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # ── Chat History ──

    async def save_chat_messages(self, messages: list[ChatMessage]) -> None:
        """메시지 목록을 DB에 저장"""
        db = _require_db(self._db)
        await db.executemany(
            "INSERT OR IGNORE INTO chat_history"
            " (id, role, content, session_name, session_uid, session_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (m.id, m.role, m.content, m.session_name, m.session_uid, m.session_id,
                 m.created_at.isoformat())
                for m in messages
            ],
        )
        await db.commit()

    async def clear_chat_history(self) -> None:
        """chat_history 테이블 전체 삭제"""
        db = _require_db(self._db)
        await db.execute("DELETE FROM chat_history")
        await db.commit()

    async def get_chat_history(self, limit: int = 50, offset: int = 0) -> list[ChatMessage]:
        """DB에서 대화 이력 조회 (최신순)"""
        db = _require_db(self._db)
        async with db.execute(
            "SELECT * FROM chat_history ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
            return [
                ChatMessage(
                    id=r["id"], role=r["role"], content=r["content"],
                    session_name=r["session_name"], session_uid=r["session_uid"],
                    session_id=r["session_id"], created_at=r["created_at"],
                )
                for r in rows
            ]

    # ── Named Sessions ──

    async def save_named_session(self, session: NamedSession, is_default: bool = False) -> None:
        """이름 세션 저장 (INSERT OR REPLACE)"""
        db = _require_db(self._db)
        await db.execute(
            "INSERT OR REPLACE INTO named_sessions"
            " (name, display_name, session_uid, working_dir, claude_session_id,"
            "  is_default, created_at, message_count)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session.name, session.display_name, session.session_uid,
             session.working_dir, session.claude_session_id,
             1 if is_default else 0,
             session.created_at.isoformat(), session.message_count),
        )
        await db.commit()

    async def delete_named_session(self, name: str) -> None:
        """이름 세션 삭제"""
        db = _require_db(self._db)
        await db.execute("DELETE FROM named_sessions WHERE name = ?", (name,))
        await db.commit()

    async def get_all_named_sessions(self) -> list[tuple[NamedSession, bool]]:
        """모든 이름 세션 조회. (NamedSession, is_default) 튜플 리스트 반환."""
        db = _require_db(self._db)
        async with db.execute(
            "SELECT * FROM named_sessions ORDER BY created_at"
        ) as cur:
            rows = await cur.fetchall()
            result = []
            for r in rows:
                session = NamedSession(
                    name=r["name"],
                    display_name=r["display_name"],
                    session_uid=r["session_uid"],
                    working_dir=r["working_dir"],
                    claude_session_id=r["claude_session_id"],
                    created_at=r["created_at"],
                    message_count=r["message_count"],
                    status=NamedSessionStatus.IDLE,
                )
                result.append((session, bool(r["is_default"])))
            return result

    async def update_named_session_default(self, name: str, is_default: bool) -> None:
        """특정 세션의 is_default 플래그만 업데이트"""
        db = _require_db(self._db)
        if is_default:
            # 기존 default 해제 후 새로 설정
            await db.execute("UPDATE named_sessions SET is_default = 0")
        await db.execute(
            "UPDATE named_sessions SET is_default = ? WHERE name = ?",
            (1 if is_default else 0, name),
        )
        await db.commit()

    async def clear_named_sessions_default(self) -> None:
        """모든 세션의 default 플래그 해제"""
        db = _require_db(self._db)
        await db.execute("UPDATE named_sessions SET is_default = 0")
        await db.commit()
