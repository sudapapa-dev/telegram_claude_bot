from __future__ import annotations

import asyncio
import logging
import os
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from src.orchestrator.manager import InstanceManager
from src.shared import ai_session as session_mod
from src.shared.ai_session import AIProvider, get_manager
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
        "메시지를 입력하면 AI가 응답합니다\\.\n\n"
        "🤖 *자율 개발 에이전트팀*\n"
        "/dev \\<요구사항\\> \\- PM→설계→개발→테스트→QA 자동 수행\n"
        "/devstatus \\[id\\] \\- 워크플로우 상태 조회\n"
        "/devcancel \\[id\\] \\- 워크플로우 취소\n\n"
        "⚙️ *시스템*\n"
        "/new \\- 새 대화 시작 \\+ AI 선택 \\(Claude/Gemini\\)\n"
        "/status \\- 시스템 상태\n"
        "/logs \\<id\\> \\[lines\\] \\- 로그 조회\n"
        "/setmodel \\<id\\> \\<model\\> \\- 모델 변경\n"
        "/history \\- 대화 이력"
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
    """새 대화 시작 - AI provider 선택 키보드 표시"""
    if not await _check_allowed(update, ctx):
        return
    from src.telegram.keyboards import ai_select_keyboard
    mgr = get_manager()
    current = mgr.provider
    text = (
        f"🆕 *새 대화 시작*\n\n"
        f"현재: {current.display_name()}\n\n"
        f"사용할 AI를 선택하세요:"
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=ai_select_keyboard(current),
    )


def _split_message(text: str, max_length: int = 3000) -> list[str]:
    """메시지를 안전하게 분할 (줄바꿈 기준으로 분할하여 마크다운 깨짐 방지)"""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > max_length:
            if current:
                chunks.append(current)
            # 단일 라인이 max_length 초과시 강제 분할
            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks


async def chat_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """일반 메시지를 상시 대기 중인 Claude Code CLI로 전달 (레거시 - 직접 호출용)"""
    if not await _check_allowed(update, ctx):
        return
    await _process_message(
        bot=ctx.bot,
        update_data=update.to_dict(),
        bot_data=dict(ctx.bot_data),
        chat_id=update.effective_chat.id,
        message_id=update.message.message_id,
        ack_message_id=None,
    )


async def _process_message(
    bot,
    update_data: dict,
    bot_data: dict,
    chat_id: int,
    message_id: int,
    ack_message_id: int | None,
) -> None:
    """실제 Claude 처리 로직 - MessageQueue 워커에서 호출됨"""
    from telegram import Update as TGUpdate, Bot

    update = TGUpdate.de_json(update_data, bot)

    async def _delete_ack() -> None:
        """수신 확인 메시지 삭제"""
        if ack_message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=ack_message_id)
            except Exception:
                pass

    async def _send_reply(reply: str) -> None:
        """응답 전송 (3000자 초과 시 파일)"""
        if len(reply) > 3000:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8"
            ) as f:
                f.write(reply)
                tmp_path = f.name
            try:
                with open(tmp_path, "rb") as f:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename="response.md",
                        caption="📄 응답이 길어 파일로 전송합니다.",
                        reply_to_message_id=message_id,
                    )
            finally:
                os.unlink(tmp_path)
        else:
            chunks = _split_message(reply)
            for chunk in chunks:
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    reply_to_message_id=message_id,
                )

    # typing 액션 주기적 갱신
    async def keep_typing() -> None:
        while True:
            try:
                await bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(4)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    # 이미지 메시지 처리
    if update.message and update.message.photo:
        photo = update.message.photo[-1]
        photo_file = await bot.get_file(photo.file_id)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        await photo_file.download_to_drive(tmp_path)
        caption = update.message.caption or "이 이미지에 대해 설명해줘"

        typing_task = asyncio.create_task(keep_typing())
        try:
            prompt = f"[이미지 첨부됨: {tmp_path}]\n{caption}"
            reply = await session_mod.ask(prompt)
            await _delete_ack()
            await _send_reply(reply)
        except Exception as e:
            logger.exception("Claude CLI 오류 (이미지)")
            await _delete_ack()
            await bot.send_message(chat_id=chat_id, text=f"❌ 오류: {e}", reply_to_message_id=message_id)
        finally:
            typing_task.cancel()
            os.unlink(tmp_path)
        return

    # 텍스트 메시지 처리
    prompt = update.message.text if update.message else None
    if not prompt:
        await _delete_ack()
        return

    typing_task = asyncio.create_task(keep_typing())
    try:
        reply = await session_mod.ask(prompt)
        await _delete_ack()
        await _send_reply(reply)
    except Exception as e:
        logger.exception("Claude CLI 오류")
        await _delete_ack()
        await bot.send_message(chat_id=chat_id, text=f"❌ 오류: {e}", reply_to_message_id=message_id)
    finally:
        typing_task.cancel()


async def dev_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """자율 개발 워크플로우 시작: /dev <요구사항>"""
    if not await _check_allowed(update, ctx):
        return

    args = ctx.args or []
    requirement = " ".join(args).strip()

    if not requirement:
        await update.message.reply_text(
            "📋 **자율 개발 에이전트팀**\n\n"
            "사용법: `/dev <요구사항>`\n\n"
            "예시:\n"
            "• `/dev 파이썬으로 간단한 계산기 CLI 앱을 만들어줘`\n"
            "• `/dev FastAPI로 TODO 앱 REST API 서버를 만들어줘`\n"
            "• `/dev 웹 스크래핑으로 뉴스 수집하는 봇을 만들어줘`\n\n"
            "AI가 PM 분석 → 설계 → 개발 → 테스트 → QA까지 자동으로 수행합니다!",
            parse_mode="Markdown",
        )
        return

    from src.agent.workflow import get_workflow_manager
    from src.telegram.keyboards import workflow_control_keyboard

    wf_mgr = get_workflow_manager()
    chat_id = update.effective_chat.id
    bot = ctx.bot

    # 시작 메시지
    start_msg = await update.message.reply_text(
        f"🚀 **자율 개발 시작!**\n\n"
        f"📝 요구사항: {requirement[:200]}\n\n"
        f"⏳ PM 분석을 시작합니다...",
        parse_mode="Markdown",
    )

    async def send_update(text: str) -> None:
        """텔레그램으로 진행 상황 전송"""
        try:
            chunks = _split_message(text, max_length=3000)
            for chunk in chunks:
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode="Markdown",
                    reply_to_message_id=start_msg.message_id,
                )
        except Exception as e:
            logger.warning("워크플로우 업데이트 전송 실패: %s", e)

    # 워크플로우 시작 (백그라운드)
    wf = await wf_mgr.start(requirement=requirement, update_callback=send_update)

    await bot.send_message(
        chat_id=chat_id,
        text=f"✅ 워크플로우 시작됨: `{wf.id}`\n진행 상황이 실시간으로 업데이트됩니다.",
        parse_mode="Markdown",
        reply_markup=workflow_control_keyboard(wf.id),
        reply_to_message_id=start_msg.message_id,
    )


async def devstatus_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/devstatus [id] - 워크플로우 상태 조회"""
    if not await _check_allowed(update, ctx):
        return

    from src.agent.workflow import get_workflow_manager, WorkflowStatus

    wf_mgr = get_workflow_manager()
    args = ctx.args or []

    if args:
        # 특정 워크플로우 상태 조회
        wf = wf_mgr.get(args[0])
        if not wf:
            await update.message.reply_text(f"❌ 워크플로우 없음: `{args[0]}`", parse_mode="Markdown")
            return

        status_emoji = {
            WorkflowStatus.PENDING: "⏳",
            WorkflowStatus.RUNNING: "🔄",
            WorkflowStatus.COMPLETED: "✅",
            WorkflowStatus.FAILED: "❌",
            WorkflowStatus.CANCELLED: "🚫",
        }
        emoji = status_emoji.get(wf.status, "❓")
        phase_info = f"\n현재 단계: {wf.current_phase.value}" if wf.current_phase and wf.status == WorkflowStatus.RUNNING else ""
        error_info = f"\n오류: {wf.error}" if wf.error else ""

        text = (
            f"{emoji} **워크플로우 상태**\n\n"
            f"ID: `{wf.id}`\n"
            f"상태: {wf.status.value}"
            f"{phase_info}"
            f"\n소요시간: {wf.elapsed()}"
            f"{error_info}\n\n"
            f"요구사항: {wf.requirement[:100]}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        # 전체 워크플로우 목록
        all_wfs = wf_mgr.list_all()
        if not all_wfs:
            await update.message.reply_text("📭 실행된 워크플로우가 없습니다.")
            return

        status_emoji = {
            WorkflowStatus.PENDING: "⏳",
            WorkflowStatus.RUNNING: "🔄",
            WorkflowStatus.COMPLETED: "✅",
            WorkflowStatus.FAILED: "❌",
            WorkflowStatus.CANCELLED: "🚫",
        }

        lines = ["📋 **워크플로우 목록**\n"]
        for wf in all_wfs[:10]:
            emoji = status_emoji.get(wf.status, "❓")
            ts = wf.created_at.strftime("%m/%d %H:%M")
            req_preview = wf.requirement[:40] + ("..." if len(wf.requirement) > 40 else "")
            lines.append(f"{emoji} `{wf.id}` [{ts}] {req_preview}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def devcancel_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/devcancel [id] - 워크플로우 취소"""
    if not await _check_allowed(update, ctx):
        return

    from src.agent.workflow import get_workflow_manager

    wf_mgr = get_workflow_manager()
    args = ctx.args or []

    if not args:
        # 실행 중인 워크플로우 모두 취소
        active = wf_mgr.active()
        if not active:
            await update.message.reply_text("ℹ️ 실행 중인 워크플로우가 없습니다.")
            return
        for wf in active:
            await wf_mgr.cancel(wf.id)
        await update.message.reply_text(f"🚫 {len(active)}개 워크플로우 취소됨")
        return

    wf_id = args[0]
    cancelled = await wf_mgr.cancel(wf_id)
    if cancelled:
        await update.message.reply_text(f"🚫 취소 요청됨: `{wf_id}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ 취소 실패 (이미 종료됨): `{wf_id}`", parse_mode="Markdown")


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
