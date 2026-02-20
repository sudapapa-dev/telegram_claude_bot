from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

from src.shared.models import ChatMessage, Instance, InstanceStatus, Task, TaskStatus

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS instances (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    working_dir TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'stopped',
    api_key TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT 'claude-sonnet-4-20250514',
    created_at TEXT NOT NULL,
    current_task_id TEXT
);

CREATE TABLE IF NOT EXISTS chat_history (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    result TEXT,
    error TEXT,
    FOREIGN KEY (instance_id) REFERENCES instances(id)
);
"""


class Database:
    """SQLite 비동기 데이터베이스"""

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """DB 연결 및 스키마 초기화"""
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        logger.info("DB 초기화 완료: %s", self._path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # ── Instances ──

    async def save_instance(self, inst: Instance) -> None:
        assert self._db
        await self._db.execute(
            """INSERT OR REPLACE INTO instances
               (id, name, working_dir, status, api_key, model, created_at, current_task_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (inst.id, inst.name, inst.working_dir, inst.status.value,
             inst.api_key, inst.model, inst.created_at.isoformat(), inst.current_task_id),
        )
        await self._db.commit()

    async def get_instance(self, instance_id: str) -> Instance | None:
        assert self._db
        async with self._db.execute(
            "SELECT * FROM instances WHERE id = ?", (instance_id,)
        ) as cur:
            row = await cur.fetchone()
            return self._row_to_instance(row) if row else None

    async def get_all_instances(self) -> list[Instance]:
        assert self._db
        async with self._db.execute("SELECT * FROM instances ORDER BY created_at") as cur:
            return [self._row_to_instance(r) for r in await cur.fetchall()]

    async def delete_instance(self, instance_id: str) -> None:
        assert self._db
        await self._db.execute("DELETE FROM tasks WHERE instance_id = ?", (instance_id,))
        await self._db.execute("DELETE FROM instances WHERE id = ?", (instance_id,))
        await self._db.commit()

    # ── Tasks ──

    async def save_task(self, task: Task) -> None:
        assert self._db
        await self._db.execute(
            """INSERT OR REPLACE INTO tasks
               (id, instance_id, prompt, status, priority, created_at,
                started_at, completed_at, result, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.id, task.instance_id, task.prompt, task.status.value, task.priority,
             task.created_at.isoformat(),
             task.started_at.isoformat() if task.started_at else None,
             task.completed_at.isoformat() if task.completed_at else None,
             task.result, task.error),
        )
        await self._db.commit()

    async def get_task(self, task_id: str) -> Task | None:
        assert self._db
        async with self._db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
            row = await cur.fetchone()
            return self._row_to_task(row) if row else None

    async def get_tasks_by_instance(self, instance_id: str, limit: int = 20) -> list[Task]:
        assert self._db
        async with self._db.execute(
            "SELECT * FROM tasks WHERE instance_id = ? ORDER BY created_at DESC LIMIT ?",
            (instance_id, limit),
        ) as cur:
            return [self._row_to_task(r) for r in await cur.fetchall()]

    async def get_pending_task_count(self) -> int:
        assert self._db
        async with self._db.execute(
            "SELECT COUNT(*) FROM tasks WHERE status IN ('pending', 'running')"
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

    # ── Chat History ──

    async def save_chat_messages(self, messages: list[ChatMessage]) -> None:
        """메시지 목록을 DB에 저장"""
        assert self._db
        await self._db.executemany(
            "INSERT OR IGNORE INTO chat_history (id, role, content, created_at) VALUES (?, ?, ?, ?)",
            [(m.id, m.role, m.content, m.created_at.isoformat()) for m in messages],
        )
        await self._db.commit()

    async def get_chat_history(self, limit: int = 50, offset: int = 0) -> list[ChatMessage]:
        """DB에서 대화 이력 조회 (최신순)"""
        assert self._db
        async with self._db.execute(
            "SELECT * FROM chat_history ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
            return [ChatMessage(id=r["id"], role=r["role"], content=r["content"], created_at=r["created_at"]) for r in rows]

    # ── Helpers ──

    @staticmethod
    def _row_to_instance(row: aiosqlite.Row) -> Instance:
        return Instance(
            id=row["id"], name=row["name"], working_dir=row["working_dir"],
            status=InstanceStatus(row["status"]), api_key=row["api_key"],
            model=row["model"], created_at=row["created_at"],
            current_task_id=row["current_task_id"],
        )

    @staticmethod
    def _row_to_task(row: aiosqlite.Row) -> Task:
        return Task(
            id=row["id"], instance_id=row["instance_id"], prompt=row["prompt"],
            status=TaskStatus(row["status"]), priority=row["priority"],
            created_at=row["created_at"], started_at=row["started_at"],
            completed_at=row["completed_at"], result=row["result"], error=row["error"],
        )
