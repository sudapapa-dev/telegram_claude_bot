"""대화 이력 저장소 - 메모리 캐시 + JSON 파일 + SQLite DB 삼중 저장"""
from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from src.shared.models import ChatMessage

if TYPE_CHECKING:
    from src.shared.database import Database

logger = logging.getLogger(__name__)

_MAX_MEMORY = 100  # 메모리/JSON 캐시에 보관할 최대 메시지 수 (DB는 무제한 영속)


class ChatHistoryStore:
    """대화 이력 관리.

    - 메모리: deque로 최근 _MAX_MEMORY 개 보관 (빠른 조회)
    - JSON 파일: 앱 재시작 후에도 이력 복원
    - SQLite DB: 장기 보관 및 검색
    """

    def __init__(self, json_path: Path, db: "Database") -> None:
        self._json_path = json_path
        self._db = db
        self._memory: deque[ChatMessage] = deque(maxlen=_MAX_MEMORY)

    async def load(self) -> None:
        """JSON 파일에서 이력 복원, 없거나 손상된 경우 DB에서 복원"""
        if self._json_path.exists():
            try:
                data = json.loads(self._json_path.read_text(encoding="utf-8"))
                for item in data[-_MAX_MEMORY:]:
                    self._memory.append(ChatMessage.model_validate(item))
                logger.info("대화 이력 복원 (JSON): %d개", len(self._memory))
                return
            except Exception:
                logger.exception("chat_history.json 로드 실패, DB에서 복원 시도")

        # JSON 없거나 손상된 경우 DB에서 복원
        try:
            messages = await self._db.get_chat_history(limit=_MAX_MEMORY)
            for m in reversed(messages):  # DB는 최신순이므로 역전하여 오래된 순으로 추가
                self._memory.append(m)
            if messages:
                logger.info("대화 이력 복원 (DB): %d개", len(self._memory))
                await self._save_json()  # DB 복원 후 JSON 동기화
            else:
                logger.info("이전 대화 이력 없음, 빈 이력으로 시작")
        except Exception:
            logger.exception("DB 대화 이력 복원 실패, 빈 이력으로 시작")

    async def append(
        self,
        role: str,
        content: str,
        *,
        session_name: str | None = None,
        session_uid: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """새 메시지 추가 — 메모리·JSON·DB에 동시 저장"""
        msg = ChatMessage(
            role=role, content=content,
            session_name=session_name, session_uid=session_uid, session_id=session_id,
        )
        self._memory.append(msg)
        await self._save_json()
        try:
            await self._db.save_chat_messages([msg])
        except Exception:
            logger.exception("DB 대화 이력 저장 실패 (무시)")

    def recent(self, n: int = 10) -> list[ChatMessage]:
        """메모리에서 최근 n개 반환 (오래된 순)"""
        items = list(self._memory)
        return items[-n:]

    async def search_db(self, limit: int = 50) -> list[ChatMessage]:
        """DB에서 최근 limit개 반환 (오래된 순)"""
        try:
            messages = await self._db.get_chat_history(limit=limit)
            return list(reversed(messages))  # DB는 최신순이므로 역전
        except Exception:
            logger.exception("DB 대화 이력 조회 실패")
            return []

    async def clear(self) -> None:
        """대화 이력 전체 초기화 — 메모리·JSON·DB 모두 삭제"""
        self._memory.clear()
        try:
            if self._json_path.exists():
                self._json_path.unlink()
        except Exception:
            logger.exception("chat_history.json 삭제 실패 (무시)")
        try:
            await self._db.clear_chat_history()
        except Exception:
            logger.exception("DB 대화 이력 삭제 실패 (무시)")
        logger.info("대화 이력 초기화 완료")

    async def _save_json(self) -> None:
        """메모리 이력을 JSON 파일에 저장"""
        try:
            items = [m.model_dump(mode="json") for m in self._memory]
            self._json_path.write_text(
                json.dumps(items, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("chat_history.json 저장 실패 (무시)")
