from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from src.shared.models import Task

logger = logging.getLogger(__name__)

TaskHandler = Callable[[Task], Coroutine[Any, Any, None]]


@dataclass(order=True)
class PrioritizedTask:
    priority: int
    task: Task = field(compare=False)


class TaskQueue:
    """우선순위 기반 비동기 작업 큐"""

    def __init__(self, max_concurrent: int = 3) -> None:
        self._queue: asyncio.PriorityQueue[PrioritizedTask] = asyncio.PriorityQueue()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._handler: TaskHandler | None = None
        self._running = False
        self._worker_task: asyncio.Task[None] | None = None

    def set_handler(self, handler: TaskHandler) -> None:
        self._handler = handler

    async def enqueue(self, task: Task) -> None:
        await self._queue.put(PrioritizedTask(priority=task.priority, task=task))
        logger.info("큐 추가: task=%s, priority=%d", task.id, task.priority)

    async def start(self) -> None:
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            async with self._semaphore:
                if self._handler:
                    try:
                        await self._handler(item.task)
                    except Exception:
                        logger.exception("작업 처리 오류: task=%s", item.task.id)
                self._queue.task_done()
