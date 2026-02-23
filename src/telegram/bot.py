from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    clean_command,
    history_command,
    logs_command, new_command, setmodel_command,
    start_command, status_command,
    task_command, taskcancel_command, taskstatus_command,
)

logger = logging.getLogger(__name__)

MAX_WORKERS = 1  # 기본값; ControlTowerBot 생성 시 session_pool_size로 재설정됨


# ── In-Flight 추적 ──────────────────────────────────────────────────────────

_MONITOR_INTERVAL = 5  # 모니터링 주기 (초)


@dataclass
class InFlightRecord:
    """Claude에 전달되어 응답 대기 중인 메시지 단위"""
    msg_queue_id: str
    chat_id: int
    message_id: int
    ack_message_id: int | None
    bot: Bot
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def elapsed_seconds(self) -> float:
        """큐 등록 후 경과 시간 (초)"""
        return (datetime.now(timezone.utc) - self.enqueued_at).total_seconds()


class InFlightRegistry:
    """Claude에 전달된 후 응답을 기다리는 메시지를 추적하는 레지스트리.

    msg_queue_id → InFlightRecord 매핑을 유지하며,
    응답이 도착하면 resolve()로 레코드를 꺼내 텔레그램으로 응답 전송.
    주기적으로 Claude 세션 상태를 모니터링하여 프로세스 종료 시 즉시 오류 알림.
    """

    def __init__(self) -> None:
        self._records: dict[str, InFlightRecord] = {}
        self._monitor_task: asyncio.Task | None = None

    def register(self, record: InFlightRecord) -> None:
        """레코드 등록"""
        self._records[record.msg_queue_id] = record
        logger.debug("in-flight 등록: msg_id=%s, total=%d", record.msg_queue_id, len(self._records))

    def resolve(self, msg_queue_id: str) -> InFlightRecord | None:
        """msg_queue_id로 레코드 조회 (제거하지 않음)"""
        return self._records.get(msg_queue_id)

    def remove(self, msg_queue_id: str) -> InFlightRecord | None:
        """레코드 제거 후 반환"""
        record = self._records.pop(msg_queue_id, None)
        logger.debug("in-flight 제거: msg_id=%s, remaining=%d", msg_queue_id, len(self._records))
        return record

    def pending_count(self) -> int:
        return len(self._records)

    def pending_ids(self) -> list[str]:
        return list(self._records.keys())

    def start_monitor(self) -> None:
        """주기적 세션 모니터링 태스크 시작"""
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(
                self._monitor_loop(), name="inflight-monitor"
            )
            logger.info("in-flight 모니터 시작 (interval=%ds)", _MONITOR_INTERVAL)

    def stop_monitor(self) -> None:
        """모니터링 태스크 중지"""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            self._monitor_task = None
            logger.info("in-flight 모니터 중지")

    async def _monitor_loop(self) -> None:
        """주기적으로 in-flight 레코드와 Claude 세션 상태를 대조.

        - 프로세스가 살아있지 않은데 레코드가 남아있으면 즉시 오류 알림
        - 경과 시간을 로그로 출력하여 장기 대기 감지
        """
        from src.shared import ai_session as session_mod

        while True:
            try:
                await asyncio.sleep(_MONITOR_INTERVAL)

                if not self._records:
                    continue

                active = {s["msg_id"]: s for s in session_mod.get_active_sessions() if s["msg_id"]}

                dead_ids: list[str] = []
                for msg_id, record in list(self._records.items()):
                    elapsed = record.elapsed_seconds()
                    session_info = active.get(msg_id)

                    if session_info is None:
                        # 세션에 해당 msg_id가 없음 → 프로세스 종료됐거나 아직 시작 전
                        logger.debug(
                            "in-flight 세션 없음: msg_id=%s, elapsed=%.1fs",
                            msg_id, elapsed,
                        )
                    elif not session_info["alive"]:
                        # 프로세스 비정상 종료
                        logger.warning(
                            "프로세스 비정상 종료 감지: msg_id=%s, pid=%s, elapsed=%.1fs",
                            msg_id, session_info["pid"], elapsed,
                        )
                        dead_ids.append(msg_id)
                    else:
                        # 정상 진행 중
                        logger.debug(
                            "세션 진행 중: msg_id=%s, pid=%s, elapsed=%.1fs",
                            msg_id, session_info["pid"], elapsed,
                        )

                # 비정상 종료된 레코드 즉시 오류 알림
                for msg_id in dead_ids:
                    record = self._records.pop(msg_id, None)
                    if record:
                        try:
                            await record.bot.send_message(
                                chat_id=record.chat_id,
                                text=(
                                    f"❌ *처리 실패* (`{record.msg_queue_id}`)\n\n"
                                    f"사유: Claude 프로세스가 예기치 않게 종료되었습니다\n"
                                    f"경과: {record.elapsed_seconds():.0f}초"
                                ),
                                parse_mode="Markdown",
                                reply_to_message_id=record.message_id,
                            )
                        except Exception:
                            logger.exception("프로세스 종료 알림 실패: msg_id=%s", msg_id)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("in-flight 모니터 오류 (계속)")

    async def send_abort_replies(self, reason: str = "세션이 종료되었습니다") -> None:
        """미응답 레코드에 원본 요청 메시지와 함께 오류 알림 전송"""
        if not self._records:
            return
        ids = list(self._records.keys())
        logger.warning("세션 종료 미응답 %d건 처리: %s", len(ids), ids)
        for msg_id in ids:
            record = self._records.pop(msg_id, None)
            if record:
                try:
                    await record.bot.send_message(
                        chat_id=record.chat_id,
                        text=(
                            f"❌ *처리 실패* (`{record.msg_queue_id}`)\n\n"
                            f"사유: {reason}\n"
                            f"경과: {record.elapsed_seconds():.0f}초"
                        ),
                        parse_mode="Markdown",
                        reply_to_message_id=record.message_id,
                    )
                except Exception:
                    logger.exception("세션 종료 알림 실패: msg_id=%s", msg_id)


# ── 메시지 큐 ────────────────────────────────────────────────────────────────

@dataclass
class _QueuedMessage:
    """큐에 쌓이는 메시지 단위"""
    update_data: dict[str, Any]
    context_bot_data: dict[str, Any]
    chat_id: int
    message_id: int
    msg_queue_id: str = field(default_factory=lambda: __import__("uuid").uuid4().hex[:8])
    ack_message_id: int | None = field(default=None)


class MessageQueue:
    """텔레그램 메시지를 큐에 쌓고 최대 workers 개씩 병렬 처리.

    수신 → 큐 저장 → in-flight 등록 → Claude 전달 → 응답 매칭 → 텔레그램 전송.
    """

    def __init__(self, bot: Bot, registry: InFlightRegistry, workers: int = MAX_WORKERS) -> None:
        self._bot = bot
        self._registry = registry
        self._workers_count = workers
        self._queue: asyncio.Queue[_QueuedMessage] = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(workers)
        self._workers: list[asyncio.Task[None]] = []
        self._running = False

    async def start(self) -> None:
        self._running = True
        for i in range(self._workers_count):
            t = asyncio.create_task(self._worker(i), name=f"msg-worker-{i}")
            self._workers.append(t)
        self._registry.start_monitor()
        logger.info("MessageQueue 시작: workers=%d", self._workers_count)

    async def stop(self) -> None:
        """큐 중지. 처리 중인 워커를 종료하고 미응답 메시지에 오류 알림 전송."""
        self._running = False
        self._registry.stop_monitor()

        # 워커 종료
        for t in self._workers:
            t.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        # 워커 종료 후 남은 in-flight 건 즉시 오류 알림
        await self._registry.send_abort_replies(reason="Claude 세션이 종료되었습니다")
        logger.info("MessageQueue 중지")

    async def enqueue(
        self,
        update_data: dict,
        bot_data: dict,
        chat_id: int,
        message_id: int,
        ack_message_id: int | None,
    ) -> str:
        """메시지를 큐에 추가하고 in-flight 등록. msg_queue_id 반환."""
        item = _QueuedMessage(
            update_data=update_data,
            context_bot_data=bot_data,
            chat_id=chat_id,
            message_id=message_id,
            ack_message_id=ack_message_id,
        )
        # in-flight 등록 (큐 진입 시점)
        self._registry.register(InFlightRecord(
            msg_queue_id=item.msg_queue_id,
            chat_id=chat_id,
            message_id=message_id,
            ack_message_id=ack_message_id,
            bot=self._bot,
        ))
        await self._queue.put(item)
        logger.info(
            "메시지 큐 추가: msg_id=%s, chat_id=%s, qsize=%d, in_flight=%d",
            item.msg_queue_id, chat_id, self._queue.qsize(), self._registry.pending_count(),
        )
        return item.msg_queue_id

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    async def _worker(self, worker_id: int) -> None:
        from src.telegram.handlers.commands import _process_message

        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            async with self._semaphore:
                try:
                    logger.info(
                        "워커-%d 처리 시작: msg_id=%s, chat_id=%s",
                        worker_id, item.msg_queue_id, item.chat_id,
                    )
                    await _process_message(
                        bot=self._bot,
                        update_data=item.update_data,
                        bot_data=item.context_bot_data,
                        chat_id=item.chat_id,
                        message_id=item.message_id,
                        ack_message_id=item.ack_message_id,
                        msg_queue_id=item.msg_queue_id,
                        registry=self._registry,
                    )
                except Exception:
                    logger.exception("워커-%d 처리 오류: msg_id=%s", worker_id, item.msg_queue_id)
                    # 오류 발생 시 in-flight에서 제거 후 사용자에게 알림
                    self._registry.remove(item.msg_queue_id)
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


# ── 봇 ──────────────────────────────────────────────────────────────────────

class ControlTowerBot:
    """telegram_claude_bot 텔레그램 봇"""

    def __init__(
        self,
        token: str,
        orchestrator: InstanceManager,
        allowed_users: list[int] | None = None,
        history_store: "ChatHistoryStore | None" = None,
        session_pool_size: int = 1,
    ) -> None:
        self.token = token
        self.orchestrator = orchestrator
        self.allowed_users = allowed_users or []
        self.history_store = history_store
        self._session_pool_size = session_pool_size
        self.app = Application.builder().token(token).build()
        self._msg_queue: MessageQueue | None = None
        self._registry = InFlightRegistry()
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
            ("clean", clean_command),
            ("history", history_command),
            ("task", task_command),
            ("taskcancel", taskcancel_command),
            ("taskstatus", taskstatus_command),
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
        self._msg_queue = MessageQueue(
            self.app.bot,
            registry=self._registry,
            workers=self._session_pool_size,
        )
        await self._msg_queue.start()
        logger.info("텔레그램 봇 시작 (병렬 큐: max=%d)", self._session_pool_size)
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
