from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

Callback = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    """비동기 이벤트 버스 - 컴포넌트 간 느슨한 결합"""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callback]] = {}

    def on(self, event: str, callback: Callback) -> None:
        """이벤트 리스너 등록"""
        self._listeners.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Callback) -> None:
        """이벤트 리스너 해제"""
        listeners = self._listeners.get(event, [])
        if callback in listeners:
            listeners.remove(callback)

    async def emit(self, event: str, data: Any = None) -> None:
        """이벤트 발행"""
        for callback in self._listeners.get(event, []):
            try:
                await callback(data)
            except Exception:
                logger.exception("이벤트 핸들러 오류: event=%s", event)
