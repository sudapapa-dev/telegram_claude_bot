from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from src.orchestrator.manager import InstanceManager
from src.telegram.keyboards import (
    confirm_keyboard, instance_detail_keyboard,
    instance_list_keyboard, task_list_keyboard,
)

logger = logging.getLogger(__name__)

WAITING_PROMPT = 1


def _mgr(ctx: ContextTypes.DEFAULT_TYPE) -> InstanceManager:
    return ctx.bot_data["orchestrator"]


def _is_allowed(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    ids: list[int] = ctx.bot_data.get("allowed_users", [])
    if not ids:
        return True
    uid = update.effective_user.id if update.effective_user else 0
    return uid in ids


async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int | None:
    query = update.callback_query
    if not query or not query.data:
        return None
    await query.answer()
    if not _is_allowed(update, ctx):
        await query.edit_message_text("\u26d4 접근이 거부되었습니다.")
        return None
    data = query.data
    mgr = _mgr(ctx)

    # 인스턴스 선택
    if data.startswith("inst:"):
        return await _show_instance_detail(query, mgr, data.split(":")[1])

    # 목록 새로고침 / 뒤로가기
    if data in ("refresh:instances", "back:instances"):
        instances = await mgr.get_all_instances()
        await query.edit_message_text("\U0001f4cb 인스턴스 목록:", reply_markup=instance_list_keyboard(instances))
        return None

    # 액션
    if data.startswith("action:"):
        parts = data.split(":", 2)
        if len(parts) < 3:
            await query.edit_message_text("❌ 잘못된 액션 데이터")
            return None
        _, action, tid = parts

        if action == "run":
            ctx.user_data["pending_run_instance"] = tid
            await query.edit_message_text(f"\U0001f4dd 프롬프트를 입력하세요 (인스턴스: `{tid}`):", parse_mode="Markdown")
            return WAITING_PROMPT

        if action == "logs":
            logs = await mgr.get_logs(tid, 30)
            text = "\n".join(logs[-30:]) if logs else "(로그 없음)"
            if len(text) > 4000:
                text = text[-4000:]
            await query.edit_message_text(f"\U0001f4cb 로그:\n```\n{text}\n```", parse_mode="Markdown")
            return None

        if action == "stop":
            await mgr.stop_instance(tid)
            await query.edit_message_text(f"\u23f9 인스턴스 중지됨: {tid}")
            return None

        if action == "delete":
            await query.edit_message_text(
                f"\u26a0\ufe0f 인스턴스 `{tid}`를 삭제하시겠습니까?",
                reply_markup=confirm_keyboard("delete", tid),
                parse_mode="Markdown",
            )
            return None

        if action == "history":
            tasks = await mgr.get_task_history(tid, 10)
            if not tasks:
                await query.edit_message_text("\U0001f4ed 작업 히스토리 없음")
                return None
            await query.edit_message_text("\U0001f4dc 작업 히스토리:", reply_markup=task_list_keyboard(tasks))
            return None


    # 확인 처리
    if data.startswith("confirm:"):
        parts = data.split(":", 2)
        if len(parts) < 3:
            await query.edit_message_text("❌ 잘못된 확인 데이터")
            return None
        _, action, tid = parts
        if action == "delete":
            await mgr.delete_instance(tid)
            await query.edit_message_text(f"\U0001f5d1 인스턴스 삭제됨: {tid}")
        return None

    if data == "cancel":
        await query.edit_message_text("\u274c 취소됨")
        return None

    # 작업 상세
    if data.startswith("task:"):
        task = await mgr.get_task(data.split(":")[1])
        if not task:
            await query.edit_message_text("\u274c 작업 없음")
            return None
        result_text = task.result or task.error or "(결과 없음)"
        if len(result_text) > 3500:
            result_text = result_text[:3500] + "\n...(잘림)"
        text = (
            f"\U0001f4cb *작업 상세*\n"
            f"ID: `{task.id}`\n상태: {task.status.value}\n"
            f"프롬프트: {task.prompt[:100]}\n\n결과:\n```\n{result_text}\n```"
        )
        await query.edit_message_text(text, parse_mode="Markdown")
        return None

    return None


async def prompt_input_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_allowed(update, ctx):
        await update.message.reply_text("\u26d4 접근이 거부되었습니다.")
        return ConversationHandler.END
    iid = ctx.user_data.pop("pending_run_instance", None)
    if not iid:
        await update.message.reply_text("\u274c 세션 만료")
        return ConversationHandler.END
    try:
        task = await _mgr(ctx).submit_task(iid, update.message.text)
        await update.message.reply_text(f"\U0001f4e8 작업 제출됨\nTask ID: `{task.id}`", parse_mode="Markdown")
    except ValueError as e:
        await update.message.reply_text(f"\u274c {e}")
    return ConversationHandler.END



async def cancel_conversation(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.pop("pending_run_instance", None)
    await update.message.reply_text("\u274c 취소됨")
    return ConversationHandler.END


async def _show_instance_detail(query, mgr: InstanceManager, instance_id: str) -> None:
    inst = await mgr.get_instance(instance_id)
    if not inst:
        await query.edit_message_text("\u274c 인스턴스 없음")
        return None
    masked = inst.api_key[:8] + "..." if len(inst.api_key) > 8 else "****"
    text = (
        f"\U0001f4e6 *{inst.name}*\n\n"
        f"ID: `{inst.id}`\n상태: {inst.status.value}\n"
        f"모델: {inst.model}\nAPI 키: {masked}\n"
        f"디렉토리: {inst.working_dir}\n"
        f"생성: {inst.created_at.strftime('%Y-%m-%d %H:%M')}"
    )
    await query.edit_message_text(text, reply_markup=instance_detail_keyboard(inst), parse_mode="Markdown")
    return None
