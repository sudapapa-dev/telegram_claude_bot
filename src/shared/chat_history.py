from __future__ import annotations

import json
import logging
from pathlib import Path

from src.shared.models import ChatMessage

logger = logging.getLogger(__name__)

JSON_MAX = 100  # JSON 파일에 유지할 최대 메시지 수


class ChatHistoryStore:
    """
    대화 이력 관리:
    - 최신 JSON_MAX개는 json_path(실행파일 폴더)에 JSON으로 유지
    - 초과분은 DB로 이관
    """

    def __init__(self, json_path: Path, db: "Database") -> None:  # type: ignore[name-defined]
        self._json_path = json_path
        self._db = db
        self._messages: list[ChatMessage] = []

    async def load(self) -> None:
        """시작 시 JSON 파일에서 메시지 로드"""
        if self._json_path.exists():
            try:
                raw = self._json_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                self._messages = [ChatMessage(**m) for m in data]
                logger.info("대화 이력 로드: %d개", len(self._messages))
            except Exception:
                logger.exception("대화 이력 JSON 로드 실패, 초기화")
                self._messages = []

    async def add(self, role: str, content: str) -> None:
        """메시지 추가 후 JSON 저장, 초과분 DB 이관"""
        msg = ChatMessage(role=role, content=content)
        self._messages.append(msg)
        await self._flush()

    async def _flush(self) -> None:
        """JSON_MAX 초과 시 오래된 메시지를 DB로 이관 후 JSON 갱신"""
        if len(self._messages) > JSON_MAX:
            overflow = self._messages[:-JSON_MAX]
            self._messages = self._messages[-JSON_MAX:]
            try:
                await self._db.save_chat_messages(overflow)
                logger.info("대화 이력 %d개 DB 이관", len(overflow))
            except Exception:
                logger.exception("DB 이관 실패")
        self._save_json()

    def _save_json(self) -> None:
        try:
            self._json_path.write_text(
                json.dumps([m.model_dump(mode="json") for m in self._messages], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("대화 이력 JSON 저장 실패")

    def recent(self, n: int = 20) -> list[ChatMessage]:
        """최근 n개 메시지 반환 (JSON 캐시에서)"""
        return self._messages[-n:]

    async def search_db(self, limit: int = 50, offset: int = 0) -> list[ChatMessage]:
        """DB에서 오래된 이력 조회"""
        return await self._db.get_chat_history(limit=limit, offset=offset)
