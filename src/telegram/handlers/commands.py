from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.orchestrator.manager import InstanceManager
from src.shared import claude_session as session_mod
from src.shared.chat_history import ChatHistoryStore

logger = logging.getLogger(__name__)


def _mgr(ctx: ContextTypes.DEFAULT_TYPE) -> InstanceManager:
    return ctx.bot_data["orchestrator"]


def _user_id(update: Update) -> int:
    return update.effective_user.id if update.effective_user else 0


async def _check_allowed(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """허용된 사용자인지 확인. 차단된 경우 메시지 전송 후 False 반환."""
    ids: list[int] = ctx.bot_data.get("allowed_users", [])
    if not ids:
        return True
    uid = _user_id(update)
    if uid in ids:
        return True
    logger.warning("차단된 사용자 접근 시도: user_id=%s", uid)
    if update.message:
        await update.message.reply_text("\u26d4 접근이 거부되었습니다.")
    return False


def _chat_id(update: Update) -> int:
    return update.effective_chat.id if update.effective_chat else 0


async def start_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_allowed(update, ctx):
        return
    text = (
        "*Claude Control Tower*\n\n"
        "메시지를 입력하면 Claude Code가 응답합니다\\.\n\n"
        "/status \\- 시스템 상태\n"
        "/logs \\<id\\> \\[lines\\] \\- 로그 조회\n"
        "/setmodel \\<id\\> \\<model\\> \\- 모델 변경\n"
        "/new \\- 새 대화 시작 \\(세션 초기화\\)"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def status_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_allowed(update, ctx):
        return
    s = await _mgr(ctx).get_status()
    text = (
        f"\U0001f4ca *시스템 상태*\n\n"
        f"인스턴스: {s.total}개\n"
        f"  \U0001f7e2 실행중: {s.running}\n"
        f"  \u2b55 대기: {s.idle}\n"
        f"  \U0001f534 중지: {s.stopped}\n"
        f"  \u26a0\ufe0f 에러: {s.error}\n\n"
        f"대기 작업: {s.pending_tasks}개"
    )
    await update.message.reply_text(text)


async def logs_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_allowed(update, ctx):
        return
    args = ctx.args or []
    if not args:
        await update.message.reply_text("사용법: /logs <instance_id> [lines]")
        return
    limit = int(args[1]) if len(args) > 1 else 30
    logs = await _mgr(ctx).get_logs(args[0], limit)
    if not logs:
        await update.message.reply_text("\U0001f4ed 로그가 없습니다.")
        return
    text = "\n".join(logs[-limit:])
    if len(text) > 4000:
        text = "...(잘림)\n" + text[-4000:]
    await update.message.reply_text(f"\U0001f4cb 로그:\n```\n{text}\n```", parse_mode="Markdown")


async def setmodel_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_allowed(update, ctx):
        return
    args = ctx.args or []
    if len(args) < 2:
        await update.message.reply_text("사용법: /setmodel <instance_id> <model>")
        return
    mgr = _mgr(ctx)
    inst = await mgr.get_instance(args[0])
    if not inst:
        await update.message.reply_text(f"\u274c 인스턴스 없음: {args[0]}")
        return
    inst.model = args[1]
    await mgr._db.save_instance(inst)
    proc = mgr._processes.get(args[0])
    if proc:
        proc.model = args[1]
    await update.message.reply_text(f"\U0001f504 모델 변경됨: {inst.name} \u2192 {args[1]}")


async def new_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """새 대화 시작 - 프로세스 재시작"""
    if not await _check_allowed(update, ctx):
        return
    await session_mod.new_session()
    await update.message.reply_text("\U0001f195 새 대화를 시작합니다. Claude CLI가 재시작됩니다.")


async def chat_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """일반 메시지를 상시 대기 중인 Claude Code CLI로 전달"""
    if not await _check_allowed(update, ctx):
        return
    prompt = update.message.text
    if not prompt:
        return

    # typing 액션을 주기적으로 갱신하는 태스크
    async def keep_typing() -> None:
        while True:
            try:
                await update.message.chat.send_action("typing")
                await asyncio.sleep(4)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    typing_task = asyncio.create_task(keep_typing())
    try:
        reply = await session_mod.ask(prompt)
        for i in range(0, len(reply), 4096):
            await update.message.reply_text(reply[i:i + 4096])
    except Exception as e:
        logger.exception("Claude CLI 오류")
        await update.message.reply_text(f"\u274c 오류: {e}")
    finally:
        typing_task.cancel()


async def history_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """대화 이력 조회. /history [n] — 최근 n개 (기본 10), /history db [n] — DB 이력"""
    if not await _check_allowed(update, ctx):
        return
    store: ChatHistoryStore | None = ctx.bot_data.get("history_store")
    if not store:
        await update.message.reply_text("\u274c 히스토리 스토어가 초기화되지 않았습니다.")
        return

    args = ctx.args or []
    use_db = len(args) > 0 and args[0].lower() == "db"
    try:
        n = int(args[1] if use_db and len(args) > 1 else args[0] if not use_db and args else 10)
    except (ValueError, IndexError):
        n = 10

    if use_db:
        messages = await store.search_db(limit=n)
        header = f"\U0001f5c4 DB 대화 이력 (최근 {n}개):\n\n"
    else:
        messages = store.recent(n)
        header = f"\U0001f4dc 최근 대화 이력 ({n}개):\n\n"

    if not messages:
        await update.message.reply_text("\U0001f4ed 대화 이력이 없습니다.")
        return

    lines: list[str] = [header]
    for m in messages:
        ts = m.created_at.strftime("%m/%d %H:%M") if hasattr(m.created_at, "strftime") else str(m.created_at)[:16]
        role_icon = "\U0001f464" if m.role == "user" else "\U0001f916"
        preview = m.content[:200].replace("\n", " ")
        lines.append(f"{role_icon} [{ts}] {preview}\n")

    text = "".join(lines)
    for i in range(0, len(text), 4096):
        await update.message.reply_text(text[i:i + 4096])
