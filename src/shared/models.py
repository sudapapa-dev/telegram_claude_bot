from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from typing import Literal

from pydantic import BaseModel, Field


class InstanceStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex[:12]


class Instance(BaseModel):
    """Claude Code 인스턴스 정보"""
    id: str = Field(default_factory=_new_id)
    name: str
    working_dir: str
    status: InstanceStatus = InstanceStatus.STOPPED
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    created_at: datetime = Field(default_factory=_utcnow)
    current_task_id: str | None = None


class Task(BaseModel):
    """실행 작업 정보"""
    id: str = Field(default_factory=_new_id)
    instance_id: str
    prompt: str
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: str | None = None
    error: str | None = None


class InstanceConfig(BaseModel):
    """인스턴스 생성 설정"""
    name: str
    working_dir: str
    api_key: str
    model: str = "claude-sonnet-4-6"


class ChatMessage(BaseModel):
    """Claude 대화 메시지 (세션 정보 포함)"""
    id: str = Field(default_factory=_new_id)
    role: Literal["user", "assistant"]
    content: str
    session_name: str | None = None      # 세션 표시 이름 (예: "suho")
    session_uid: str | None = None       # 세션 고유 ID (12자리 hex)
    session_id: str | None = None        # Claude CLI session_id
    created_at: datetime = Field(default_factory=_utcnow)


class SystemStatus(BaseModel):
    """전체 시스템 상태 요약"""
    total: int = 0
    running: int = 0
    idle: int = 0
    stopped: int = 0
    error: int = 0
    pending_tasks: int = 0


class NamedSessionStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    DEAD = "dead"


class NamedSession(BaseModel):
    """이름 기반 Claude 세션 정보"""
    name: str                                         # 고유 식별자 (소문자, 영문/숫자/한글)
    display_name: str                                 # 표시 이름 (원본 대소문자 유지)
    session_uid: str = Field(default_factory=lambda: uuid4().hex[:12])  # 불변 고유 ID (폴더명 등에 사용)
    working_dir: str                                  # 작업 디렉토리
    status: NamedSessionStatus = NamedSessionStatus.IDLE
    claude_session_id: str | None = None              # Claude --resume에 사용
    created_at: datetime = Field(default_factory=_utcnow)
    last_used_at: datetime | None = None
    message_count: int = 0
    last_error: str | None = None
