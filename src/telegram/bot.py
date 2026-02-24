from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from telegram import Bot
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, filters,
)

from src.shared.chat_history import ChatHistoryStore
from src.shared.named_sessions import NamedSessionManager

if TYPE_CHECKING:
    from src.shared.database import Database

from src.telegram.handlers.commands import (
    clean_command,
    close_command,
    default_command,
    history_command,
    new_command, open_command,
    start_command, status_command,
)

logger = logging.getLogger(__name__)


# ── 메시지 큐 ────────────────────────────────────────────────────────────────

@dataclass
class _QueuedMessage:
    """큐에 쌓이는 메시지 단위"""
    update_data: dict[str, Any]
    context_bot_data: dict[str, Any]
    chat_id: int
    message_id: int = 0
    ack_message_id: int | None = field(default=None)
    text_preview: str = ""      # 메시지 내용 앞부분 (표시용)
    target_session: str = ""    # 라우팅 대상 세션 이름 (기본세션이면 빈 문자열)
    enqueued_at: float = field(default_factory=lambda: __import__("time").monotonic())
    started_at: float | None = None  # 처리 시작 시각 (monotonic)


class MessageQueue:
    """텔레그램 메시지를 비동기 병렬 처리.

    수신 → 큐 저장 → Claude 전달(비동기 fire-and-forget) → 텔레그램 전송.
    서로 다른 세션의 메시지는 동시 처리되고,
    같은 세션의 메시지는 NamedSessionManager 내부 Lock으로 순서 보장.
    """

    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._queue: asyncio.Queue[_QueuedMessage] = asyncio.Queue()
        self._dispatcher_task: asyncio.Task[None] | None = None
        self._running = False
        self._processing: list[_QueuedMessage] = []  # 현재 처리 중인 항목들
        self._active_tasks: set[asyncio.Task[None]] = set()  # 비동기 처리 태스크 추적

    async def start(self) -> None:
        self._running = True
        self._dispatcher_task = asyncio.create_task(
            self._dispatcher(), name="msg-dispatcher"
        )
        logger.info("MessageQueue 시작: 비동기 병렬 처리 모드")

    async def stop(self) -> None:
        """큐 중지. 처리 중인 태스크를 종료."""
        self._running = False

        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass

        # 진행 중인 모든 처리 태스크 취소
        for task in list(self._active_tasks):
            task.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
        self._active_tasks.clear()
        self._processing.clear()
        logger.info("MessageQueue 중지")

    async def enqueue(
        self,
        update_data: dict,
        bot_data: dict,
        chat_id: int,
        message_id: int,
        ack_message_id: int | None,
        text_preview: str = "",
        target_session: str = "",
    ) -> None:
        """메시지를 큐에 추가."""
        item = _QueuedMessage(
            update_data=update_data,
            context_bot_data=bot_data,
            chat_id=chat_id,
            message_id=message_id,
            ack_message_id=ack_message_id,
            text_preview=text_preview[:20],
            target_session=target_session,
        )
        await self._queue.put(item)
        logger.info(
            "메시지 큐 추가: chat_id=%s, session=%s, qsize=%d",
            chat_id, target_session or "(기본)", self._queue.qsize(),
        )

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    def get_jobs(self) -> list[dict]:
        """현재 처리 중 + 대기 중인 항목 목록 반환.

        각 항목: message_id, target, elapsed_sec, started_at(ISO), text
        """
        import time
        from datetime import datetime, timezone

        now = time.monotonic()
        epoch_offset = time.time() - now  # monotonic → wallclock 변환용

        def _to_wallclock(mono: float) -> str:
            wall = mono + epoch_offset
            return datetime.fromtimestamp(wall, tz=timezone.utc).strftime("%H:%M:%S")

        jobs: list[dict] = []

        for item in self._processing:
            started = item.started_at or item.enqueued_at
            jobs.append({
                "status": "처리중",
                "message_id": item.message_id,
                "target": item.target_session or "(기본)",
                "elapsed": int(now - started),
                "started_at": _to_wallclock(started),
                "text": item.text_preview,
            })

        try:
            for item in list(self._queue._queue):  # type: ignore[attr-defined]
                jobs.append({
                    "status": "대기중",
                    "message_id": item.message_id,
                    "target": item.target_session or "(기본)",
                    "elapsed": int(now - item.enqueued_at),
                    "started_at": "-",
                    "text": item.text_preview,
                })
        except Exception:
            pass

        return jobs

    async def _dispatcher(self) -> None:
        """큐에서 메시지를 꺼내 즉시 비동기 태스크로 실행 (fire-and-forget)."""
        from src.telegram.handlers.commands import _process_message

        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            import time as _time
            item.started_at = _time.monotonic()
            self._processing.append(item)

            task = asyncio.create_task(
                self._handle_item(item, _process_message),
                name=f"msg-{item.target_session or 'default'}-{item.message_id}",
            )
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)

            logger.info(
                "메시지 디스패치: chat_id=%s, session=%s, active=%d",
                item.chat_id, item.target_session or "(기본)", len(self._active_tasks),
            )
            self._queue.task_done()

    async def _handle_item(self, item: _QueuedMessage, process_fn) -> None:  # type: ignore[type-arg]
        """개별 메시지 처리 (비동기 태스크로 실행됨)."""
        try:
            await process_fn(
                bot=self._bot,
                update_data=item.update_data,
                bot_data=item.context_bot_data,
                chat_id=item.chat_id,
                message_id=item.message_id,
                ack_message_id=item.ack_message_id,
            )
        except Exception:
            logger.exception("메시지 처리 오류: chat_id=%s, session=%s", item.chat_id, item.target_session)
            try:
                await self._bot.send_message(
                    chat_id=item.chat_id,
                    text="❌ 메시지 처리 중 오류가 발생했습니다.",
                    reply_to_message_id=item.message_id,
                )
            except Exception:
                pass
        finally:
            if item in self._processing:
                self._processing.remove(item)


# ── 봇 ──────────────────────────────────────────────────────────────────────

class TelegramClaudeBot:
    """telegram_claude_bot 텔레그램 봇"""

    def __init__(
        self,
        token: str,
        allowed_users: list[int] | None = None,
        history_store: ChatHistoryStore | None = None,
        default_session_name: str | None = None,
        db: Database | None = None,
    ) -> None:
        self.token = token
        self.allowed_users = allowed_users or []
        self.history_store = history_store
        self.default_session_name = default_session_name
        self._db = db
        self.app = Application.builder().token(token).build()
        self._msg_queue: MessageQueue | None = None
        self._register_handlers()

    def _register_handlers(self) -> None:
        for name, handler in [
            ("start", start_command), ("help", start_command),
            ("status", status_command),
            ("clean", clean_command),
            ("history", history_command),
            ("new", new_command),
            ("open", open_command),
            ("close", close_command),
            ("default", default_command),
        ]:
            self.app.add_handler(CommandHandler(name, handler))
        self.app.add_handler(CommandHandler("job", self._job_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._enqueue_handler))
        self.app.add_handler(MessageHandler(filters.PHOTO, self._enqueue_handler))

    async def _enqueue_handler(self, update, ctx) -> None:
        """메시지를 큐에 넣고 즉시 수신 확인 메시지 전송"""
        from src.telegram.handlers.commands import _check_allowed
        if not await _check_allowed(update, ctx):
            return

        # @ 단독 입력 → 세션 목록 표시 (큐에 넣지 않고 즉시 응답)
        raw_text = (update.message.text or "").strip() if update.message else ""
        if raw_text == "@":
            from src.telegram.handlers.commands import _show_session_list
            await _show_session_list(update, ctx)
            return

        chat_id = update.effective_chat.id
        message_id = update.message.message_id

        if self._msg_queue:
            raw_text = (update.message.text or update.message.caption or "") if update.message else ""
            # target_session 미리 파악 (표시 목적)
            named_mgr = ctx.bot_data.get("named_session_manager")
            target_session = ""
            if named_mgr:
                parsed = named_mgr.parse_address(raw_text)
                if parsed:
                    target_session = parsed[0]
                elif named_mgr.default_session:
                    target_session = named_mgr.default_session.display_name

            # ACK 메시지 전송 (세션 이름 포함)
            session_label = f"[{target_session}] " if target_session else ""
            ack = await update.message.reply_text(f"⏳ {session_label}처리 중...")

            await self._msg_queue.enqueue(
                update_data=update.to_dict(),
                bot_data=dict(ctx.bot_data),
                chat_id=chat_id,
                message_id=message_id,
                ack_message_id=ack.message_id,
                text_preview=raw_text,
                target_session=target_session,
            )

    async def _job_command(self, update, ctx) -> None:
        """/job - 처리 중 및 대기 중인 메시지 목록 조회"""
        from src.telegram.handlers.commands import _check_allowed
        if not await _check_allowed(update, ctx):
            return

        if not self._msg_queue:
            await update.message.reply_text("❌ 메시지 큐가 초기화되지 않았습니다.")
            return

        jobs = self._msg_queue.get_jobs()
        if not jobs:
            await update.message.reply_text("✅ 처리 중인 작업이 없습니다.")
            return

        # 컬럼 너비 계산
        id_w   = max(len("메시지ID"), max(len(str(j["message_id"])) for j in jobs))
        tgt_w  = max(len("타겟"), max(len(j["target"]) for j in jobs))
        ela_w  = max(len("진행시간"), max(len(f"{j['elapsed']}s") for j in jobs))
        sta_w  = max(len("시작시각"), max(len(j["started_at"]) for j in jobs))
        txt_w  = max(len("메시지원문"), max(len(j["text"]) for j in jobs))

        div = f"+{'-'*(id_w+2)}+{'-'*(tgt_w+2)}+{'-'*(ela_w+2)}+{'-'*(sta_w+2)}+{'-'*(txt_w+2)}+"
        hdr = f"| {'메시지ID':{id_w}} | {'타겟':{tgt_w}} | {'진행시간':{ela_w}} | {'시작시각':{sta_w}} | {'메시지원문':{txt_w}} |"

        rows = [div, hdr, div]
        for j in jobs:
            status_icon = "🔄" if j["status"] == "처리중" else "⏳"
            elapsed_str = f"{j['elapsed']}s"
            rows.append(
                f"| {str(j['message_id']):{id_w}} | {j['target']:{tgt_w}} | {elapsed_str:{ela_w}} | {j['started_at']:{sta_w}} | {j['text']:{txt_w}} |"
            )
        rows.append(div)

        processing_cnt = sum(1 for j in jobs if j["status"] == "처리중")
        pending_cnt = sum(1 for j in jobs if j["status"] == "대기중")
        summary = f"🔄 처리중: {processing_cnt}개  ⏳ 대기중: {pending_cnt}개"

        await update.message.reply_text(
            f"{summary}\n```\n{chr(10).join(rows)}\n```",
            parse_mode="Markdown",
        )

    async def _notify_all(self, text: str) -> None:
        for cid in self.allowed_users:
            try:
                await self.app.bot.send_message(chat_id=cid, text=text, parse_mode="Markdown")
            except Exception:
                logger.exception("알림 실패: chat_id=%s", cid)

    async def initialize(self) -> None:
        self.app.bot_data["allowed_users"] = self.allowed_users
        self.app.bot_data["history_store"] = self.history_store
        self.app.bot_data["default_session_name"] = self.default_session_name
        named_mgr = NamedSessionManager(db=self._db)
        named_mgr.add_restart_callback(self._on_session_restarted)
        self.app.bot_data["named_session_manager"] = named_mgr

        # DB에서 이전 세션 복원
        restored = await named_mgr.load_from_db()
        if restored:
            logger.info("DB에서 세션 %d개 복원됨", restored)

        # 기본 세션 이름이 설정된 경우 named session으로 자동 생성 + default 지정
        if self.default_session_name:
            from src.shared.ai_session import _make_working_dir
            try:
                await named_mgr.create(
                    self.default_session_name,
                    working_dir=_make_working_dir("default"),
                )
            except ValueError:
                pass  # 이미 존재하면 무시 (DB에서 복원됨)
            await named_mgr.set_default(self.default_session_name)
            logger.info("기본 named session 설정: name=%s", self.default_session_name)

    async def _on_session_restarted(self, session_name: str, error_msg: str) -> None:
        """DEAD 세션 자동 재시작 시 사용자에게 알림"""
        text = (
            f"⚠️ 세션 *{session_name}* 이 오류로 종료되어 자동 재시작되었습니다.\n"
            f"오류: `{error_msg[:200]}`\n"
            f"대화 이력이 초기화되었습니다."
        )
        await self._notify_all(text)

    async def run(self) -> None:
        await self.initialize()
        await self.app.initialize()
        self._msg_queue = MessageQueue(bot=self.app.bot)
        await self._msg_queue.start()
        # 이름 세션 모니터 시작 + 프로세스 즉시 기동
        named_mgr: NamedSessionManager = self.app.bot_data["named_session_manager"]
        await named_mgr.start_monitor()
        asyncio.create_task(named_mgr.start_all(), name="named-session-start-all")
        logger.info("텔레그램 봇 시작")
        await self.app.start()
        await self.app.updater.start_polling()
        # 시작 알림
        default = named_mgr.default_session
        if default:
            msg = f"🚀 봇이 시작되었습니다. {default.display_name}에게 명령을 내려주세요 😊"
        else:
            msg = "🚀 봇이 시작되었습니다."
        for cid in self.allowed_users:
            try:
                await self.app.bot.send_message(chat_id=cid, text=msg)
                logger.info("시작 알림 전송: chat_id=%s", cid)
            except Exception:
                logger.exception("시작 알림 실패: chat_id=%s", cid)

    async def stop(self) -> None:
        logger.info("텔레그램 봇 중지")
        # 이름 세션 모니터 중지
        named_mgr: NamedSessionManager | None = self.app.bot_data.get("named_session_manager")
        if named_mgr:
            await named_mgr.stop_monitor()
            await named_mgr.stop_all()
        if self._msg_queue:
            await self._msg_queue.stop()
        if self.app.updater and self.app.updater.running:
            await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
