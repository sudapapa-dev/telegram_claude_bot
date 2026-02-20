from __future__ import annotations

import logging

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
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

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
        logger.info("텔레그램 봇 시작")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

    async def stop(self) -> None:
        logger.info("텔레그램 봇 중지")
        if self.app.updater and self.app.updater.running:
            await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
