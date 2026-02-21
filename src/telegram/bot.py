from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from telegram import Bot
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ConversationHandler, MessageHandler, filters,
)

from src.orchestrator.manager import InstanceManager
from src.shared.chat_history import ChatHistoryStore
from src.shared.events import EventBus
from src.shared.models import Task
from src.telegram.handlers.callbacks import (
    WAITING_PROMPT,
    callback_handler,
    cancel_conversation, prompt_input_handler,
)
from src.telegram.handlers.commands import (
    chat_handler,
    history_command,
    logs_command, new_command, setmodel_command,
    start_command, status_command,
)

logger = logging.getLogger(__name__)

MAX_WORKERS = 5  # 최대 병렬 처리 수


@dataclass
class _QueuedMessage:
    """큐에 쌓이는 메시지 단위"""
    update_data: dict[str, Any]       # update.to_dict()
    context_bot_data: dict[str, Any]  # ctx.bot_data 복사본
    chat_id: int
    message_id: int
    ack_message_id: int | None = field(default=None)  # "처리 중..." 메시지 ID


class MessageQueue:
    """텔레그램 메시지를 큐에 쌓고 최대 MAX_WORKERS 개씩 병렬 처리"""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._queue: asyncio.Queue[_QueuedMessage] = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(MAX_WORKERS)
        self._workers: list[asyncio.Task[None]] = []
        self._running = False

    async def start(self) -> None:
        self._running = True
        for i in range(MAX_WORKERS):
            t = asyncio.create_task(self._worker(i), name=f"msg-worker-{i}")
            self._workers.append(t)
        logger.info("MessageQueue 시작: workers=%d", MAX_WORKERS)

    async def stop(self) -> None:
        self._running = False
        for t in self._workers:
            t.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("MessageQueue 중지")

    async def enqueue(self, update_data: dict, bot_data: dict, chat_id: int, message_id: int, ack_message_id: int | None) -> None:
        item = _QueuedMessage(
            update_data=update_data,
            context_bot_data=bot_data,
            chat_id=chat_id,
            message_id=message_id,
            ack_message_id=ack_message_id,
        )
        await self._queue.put(item)
        logger.info("메시지 큐 추가: chat_id=%s, qsize=%d", chat_id, self._queue.qsize())

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    async def _worker(self, worker_id: int) -> None:
        from telegram import Update
        from telegram.ext import CallbackContext
        from src.telegram.handlers.commands import _process_message  # 아래에서 분리

        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            async with self._semaphore:
                try:
                    logger.info("워커-%d 처리 시작: chat_id=%s", worker_id, item.chat_id)
                    await _process_message(
                        bot=self._bot,
                        update_data=item.update_data,
                        bot_data=item.context_bot_data,
                        chat_id=item.chat_id,
                        message_id=item.message_id,
                        ack_message_id=item.ack_message_id,
                    )
                except Exception:
                    logger.exception("워커-%d 처리 오류: chat_id=%s", worker_id, item.chat_id)
                    try:
                        await self._bot.send_message(
                            chat_id=item.chat_id,
                            text="❌ 메시지 처리 중 오류가 발생했습니다.",
                            reply_to_message_id=item.message_id,
                        )
                    except Exception:
                        pass
                finally:
                    self._queue.task_done()


class ControlTowerBot:
    """Claude Control Tower 텔레그램 봇"""

    def __init__(
        self,
        token: str,
        orchestrator: InstanceManager,
        allowed_users: list[int] | None = None,
        history_store: "ChatHistoryStore | None" = None,  # type: ignore[name-defined]
    ) -> None:
        self.token = token
        self.orchestrator = orchestrator
        self.allowed_users = allowed_users or []
        self.history_store = history_store
        self.app = Application.builder().token(token).build()
        self._msg_queue: MessageQueue | None = None
        self._register_handlers()

    def _register_handlers(self) -> None:
        conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(callback_handler)],
            states={
                WAITING_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_input_handler)],
            },
            fallbacks=[CommandHandler("cancel", cancel_conversation)],
            per_message=False,
        )
        for name, handler in [
            ("start", start_command), ("help", start_command),
            ("status", status_command),
            ("logs", logs_command),
            ("setmodel", setmodel_command),
            ("new", new_command),
            ("history", history_command),
        ]:
            self.app.add_handler(CommandHandler(name, handler))
        self.app.add_handler(conv)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._enqueue_handler))
        self.app.add_handler(MessageHandler(filters.PHOTO, self._enqueue_handler))

    async def _enqueue_handler(self, update, ctx) -> None:
        """메시지를 큐에 넣고 즉시 수신 확인 메시지 전송"""
        from src.telegram.handlers.commands import _check_allowed
        if not await _check_allowed(update, ctx):
            return

        chat_id = update.effective_chat.id
        message_id = update.message.message_id
        qsize = self._msg_queue.pending_count if self._msg_queue else 0

        # 즉시 수신 확인 (큐 위치 표시)
        if qsize > 0:
            ack = await update.message.reply_text(f"⏳ 대기 중... (앞에 {qsize}개)")
        else:
            ack = await update.message.reply_text("⏳ 처리 중...")

        if self._msg_queue:
            await self._msg_queue.enqueue(
                update_data=update.to_dict(),
                bot_data=dict(ctx.bot_data),
                chat_id=chat_id,
                message_id=message_id,
                ack_message_id=ack.message_id,
            )

    def setup_notifications(self, event_bus: EventBus) -> None:
        event_bus.on("task:completed", self._on_task_completed)
        event_bus.on("task:failed", self._on_task_failed)

    async def _on_task_completed(self, task: Task) -> None:
        preview = (task.result or "")[:200]
        await self._notify_all(f"\u2705 작업 완료\nTask: `{task.id}`\nInstance: {task.instance_id}\n\n{preview}")

    async def _on_task_failed(self, task: Task) -> None:
        err = (task.error or "알 수 없는 오류")[:200]
        await self._notify_all(f"\u274c 작업 실패\nTask: `{task.id}`\nInstance: {task.instance_id}\n\n오류: {err}")

    async def _notify_all(self, text: str) -> None:
        for cid in self.allowed_users:
            try:
                await self.app.bot.send_message(chat_id=cid, text=text, parse_mode="Markdown")
            except Exception:
                logger.exception("알림 실패: chat_id=%s", cid)

    async def initialize(self) -> None:
        self.app.bot_data["orchestrator"] = self.orchestrator
        self.app.bot_data["allowed_users"] = self.allowed_users
        self.app.bot_data["history_store"] = self.history_store

    async def run(self) -> None:
        await self.initialize()
        await self.app.initialize()
        # MessageQueue는 bot 객체가 준비된 후 시작
        self._msg_queue = MessageQueue(self.app.bot)
        await self._msg_queue.start()
        logger.info("텔레그램 봇 시작 (병렬 큐: max=%d)", MAX_WORKERS)
        await self.app.start()
        await self.app.updater.start_polling()

    async def stop(self) -> None:
        logger.info("텔레그램 봇 중지")
        if self._msg_queue:
            await self._msg_queue.stop()
        if self.app.updater and self.app.updater.running:
            await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
