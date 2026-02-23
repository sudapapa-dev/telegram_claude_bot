from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import uuid
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

from src.orchestrator.manager import InstanceManager
from src.shared import ai_session as session_mod
from src.shared.chat_history import ChatHistoryStore

if TYPE_CHECKING:
    from src.telegram.bot import InFlightRegistry

logger = logging.getLogger(__name__)

# 응답 헤더 파싱 패턴: [MSG_HEADER:xxxxxxxx]
_HEADER_RE = re.compile(r"^\[MSG_HEADER:([a-f0-9]{8,16})\]\n?", re.MULTILINE)


def _inject_header_instruction(prompt: str, msg_queue_id: str) -> str:
    """프롬프트 끝에 응답 헤더 포함 지시문 추가"""
    return (
        f"{prompt}\n\n"
        f"---\n"
        f"[SYSTEM] 응답의 첫 줄은 반드시 다음 형식으로 시작하세요 (다른 내용 없이):\n"
        f"[MSG_HEADER:{msg_queue_id}]\n"
        f"이 헤더 다음 줄부터 실제 응답을 작성하세요."
    )


def _extract_header(response: str) -> tuple[str | None, str]:
    """응답에서 MSG_HEADER 추출. (msg_queue_id, 헤더 제거된 응답) 반환."""
    m = _HEADER_RE.match(response.lstrip())
    if m:
        return m.group(1), response[response.index(m.group(0)) + len(m.group(0)):].strip()
    return None, response

# 실행 중인 백그라운드 작업 목록 {chat_id: {task_id: asyncio.Task}}
# 사용자별로 격리하여 다른 사용자의 작업을 취소할 수 없도록 함
_task_sessions: dict[int, dict[str, asyncio.Task]] = {}


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
        "*telegram_claude_bot*\n\n"
        "메시지를 입력하면 Claude가 응답합니다\\.\n\n"
        "⚡ *백그라운드 작업 \\(대화 블로킹 없음\\)*\n"
        "/task \\<지시\\> \\- 독립 세션으로 작업 실행\n"
        "/taskstatus \\- 실행 중인 작업 목록\n"
        "/taskcancel \\[id\\] \\- 작업 취소\n\n"
        "⚙️ *시스템*\n"
        "/new \\- 새 대화 시작\n"
        "/clean \\- 대화 이력 및 캐시 초기화\n"
        "/status \\- 시스템 상태\n"
        "/logs \\<id\\> \\[lines\\] \\- 로그 조회\n"
        "/setmodel \\<id\\> \\<model\\> \\- 모델 변경\n"
        "/history \\- 대화 이력"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def status_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_allowed(update, ctx):
        return
    from src.shared import ai_session as session_mod
    s = await _mgr(ctx).get_status()
    pool = session_mod.get_pool_status()
    text = (
        f"\U0001f4ca *시스템 상태*\n\n"
        f"인스턴스: {s.total}개\n"
        f"  \U0001f7e2 실행중: {s.running}\n"
        f"  \u2b55 대기: {s.idle}\n"
        f"  \U0001f534 중지: {s.stopped}\n"
        f"  \u26a0\ufe0f 에러: {s.error}\n\n"
        f"대기 작업: {s.pending_tasks}개\n\n"
        f"Claude 세션 풀: {pool['total']}/{pool['pool_size']}개\n"
        f"  \U0001f7e2 idle: {pool['idle']}\n"
        f"  \U0001f7e1 busy: {pool['busy']}"
    )
    await update.message.reply_text(text)


async def logs_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_allowed(update, ctx):
        return
    args = ctx.args or []
    if not args:
        await update.message.reply_text("사용법: /logs <instance_id> [lines]")
        return
    try:
        limit = min(int(args[1]), 200) if len(args) > 1 else 30
    except ValueError:
        await update.message.reply_text("❌ lines는 숫자여야 합니다.")
        return
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
    await mgr.update_model(args[0], args[1])
    await update.message.reply_text(f"\U0001f504 모델 변경됨: {inst.name} \u2192 {args[1]}")


async def new_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """새 대화 시작 - 현재 Claude 세션을 종료하고 새로 시작"""
    if not await _check_allowed(update, ctx):
        return
    await session_mod.new_session()
    await update.message.reply_text("🆕 새 대화를 시작했습니다.")


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
        msg_queue_id=None,
        registry=None,
    )


async def _process_message(
    bot,
    update_data: dict,
    bot_data: dict,
    chat_id: int,
    message_id: int,
    ack_message_id: int | None,
    msg_queue_id: str | None = None,
    registry: "InFlightRegistry | None" = None,
) -> None:
    """실제 Claude 처리 로직 - MessageQueue 워커에서 호출됨.

    msg_queue_id가 있으면 프롬프트에 헤더 지시문을 주입하고,
    응답에서 헤더를 파싱하여 registry에서 원본 요청을 찾아 응답 전송.
    registry가 None이면 (레거시 경로) 현재 컨텍스트로 직접 응답.
    """
    from telegram import Update as TGUpdate

    update = TGUpdate.de_json(update_data, bot)

    async def _delete_ack() -> None:
        if ack_message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=ack_message_id)
            except Exception:
                pass

    async def _send_to(target_bot, target_chat_id: int, target_msg_id: int, reply: str) -> None:
        """지정된 chat/message로 응답 전송 (3000자 초과 시 파일)"""
        if len(reply) > 3000:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8"
            ) as f:
                f.write(reply)
                tmp_path = f.name
            try:
                with open(tmp_path, "rb") as f:
                    await target_bot.send_document(
                        chat_id=target_chat_id,
                        document=f,
                        filename="response.md",
                        caption="📄 응답이 길어 파일로 전송합니다.",
                        reply_to_message_id=target_msg_id,
                    )
            finally:
                os.unlink(tmp_path)
        else:
            chunks = _split_message(reply)
            for chunk in chunks:
                await target_bot.send_message(
                    chat_id=target_chat_id,
                    text=chunk,
                    reply_to_message_id=target_msg_id,
                )

    async def _send_reply(reply: str) -> None:
        """현재 컨텍스트로 응답 전송"""
        await _send_to(bot, chat_id, message_id, reply)

    async def _dispatch_reply(raw_reply: str) -> None:
        """헤더 파싱 후 registry 매칭 또는 폴백으로 응답 전송.
        registry가 None이면 현재 컨텍스트로 직접 전송.
        """
        if registry is None or msg_queue_id is None:
            # 레거시 경로: 헤더 없이 현재 컨텍스트로 전송
            await _send_reply(raw_reply)
            return

        extracted_id, clean_reply = _extract_header(raw_reply)

        if extracted_id:
            record = registry.remove(extracted_id)
            if record:
                logger.info("응답 매칭 성공: msg_id=%s → chat_id=%s", extracted_id, record.chat_id)
                # registry에서 찾은 ack 메시지 삭제
                if record.ack_message_id:
                    try:
                        await record.bot.delete_message(
                            chat_id=record.chat_id, message_id=record.ack_message_id
                        )
                    except Exception:
                        pass
                await _send_to(record.bot, record.chat_id, record.message_id, clean_reply)
            else:
                # 이미 처리됐거나 레코드 없음 → 폴백
                logger.warning("registry에 레코드 없음: msg_id=%s, 폴백 전송", extracted_id)
                await _send_reply(clean_reply)
        else:
            # 헤더 파싱 실패 → msg_queue_id로 직접 제거 후 폴백
            logger.warning("헤더 파싱 실패: msg_queue_id=%s, 폴백 전송", msg_queue_id)
            registry.remove(msg_queue_id)
            await _delete_ack()
            await _send_reply(raw_reply)

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
            base_prompt = f"[이미지 첨부됨: image.jpg]\n{caption}"
            prompt = _inject_header_instruction(base_prompt, msg_queue_id) if msg_queue_id else base_prompt
            raw_reply = await session_mod.ask(prompt)
            await _dispatch_reply(raw_reply)
        except Exception as e:
            logger.exception("Claude CLI 오류 (이미지)")
            if registry and msg_queue_id:
                registry.remove(msg_queue_id)
            await _delete_ack()
            await bot.send_message(chat_id=chat_id, text=f"❌ 오류: {e}", reply_to_message_id=message_id)
        finally:
            typing_task.cancel()
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return

    # 텍스트 메시지 처리
    prompt = update.message.text if update.message else None
    if not prompt:
        if registry and msg_queue_id:
            registry.remove(msg_queue_id)
        await _delete_ack()
        return

    typing_task = asyncio.create_task(keep_typing())
    try:
        full_prompt = _inject_header_instruction(prompt, msg_queue_id) if msg_queue_id else prompt
        raw_reply = await session_mod.ask(full_prompt)
        await _dispatch_reply(raw_reply)
    except Exception as e:
        logger.exception("Claude CLI 오류")
        if registry and msg_queue_id:
            registry.remove(msg_queue_id)
        await _delete_ack()
        await bot.send_message(chat_id=chat_id, text=f"❌ 오류: {e}", reply_to_message_id=message_id)
    finally:
        typing_task.cancel()


async def _run_task(
    task_id: str,
    prompt: str,
    chat_id: int,
    orig_msg_id: int,
    bot,
    history_store: "ChatHistoryStore | None" = None,
) -> None:
    """백그라운드 작업 실행 - 독립 Claude 세션 사용"""
    from src.shared.ai_session import ClaudeSession

    session = ClaudeSession()
    result: str = ""
    error: str | None = None
    try:
        await session.start()
        result = await session.ask(prompt, timeout=1800)
        # 대화 이력 저장 (task 접두어로 구분)
        if history_store is not None:
            await history_store.append(role="user", content=f"[task:{task_id}] {prompt}")
            await history_store.append(role="assistant", content=result)
    except asyncio.CancelledError:
        error = "취소됨"
    except Exception as e:
        error = str(e)
        logger.exception("백그라운드 작업 실패: id=%s", task_id)
    finally:
        await session.stop()
        user_tasks = _task_sessions.get(chat_id, {})
        user_tasks.pop(task_id, None)

    if error and error != "취소됨":
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ *작업 실패* (`{task_id}`)\n\n{error[:500]}",
            parse_mode="Markdown",
            reply_to_message_id=orig_msg_id,
        )
    elif error == "취소됨":
        await bot.send_message(
            chat_id=chat_id,
            text=f"🚫 *작업 취소됨* (`{task_id}`)",
            parse_mode="Markdown",
            reply_to_message_id=orig_msg_id,
        )
    else:
        chunks = _split_message(result or "(결과 없음)")
        for chunk in chunks:
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                reply_to_message_id=orig_msg_id,
            )


async def task_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/task <지시> - 독립 작업 세션으로 백그라운드 실행 (메인 대화 블로킹 없음)"""
    if not await _check_allowed(update, ctx):
        return

    args = ctx.args or []
    prompt = " ".join(args).strip()

    if not prompt:
        await update.message.reply_text(
            "⚡ *독립 작업 세션*\n\n"
            "사용법: `/task <지시>`\n\n"
            "예시:\n"
            "• `/task D:/project에 README.md 작성해줘`\n"
            "• `/task D:/myapp 전체 코드 리뷰해줘`\n\n"
            "작업 중에도 일반 대화가 가능합니다.\n"
            "완료되면 결과를 알려드립니다.",
            parse_mode="Markdown",
        )
        return

    task_id = uuid.uuid4().hex[:8]
    chat_id = update.effective_chat.id
    bot = ctx.bot
    orig_msg_id = update.message.message_id
    history_store: ChatHistoryStore | None = ctx.bot_data.get("history_store")

    task = asyncio.create_task(
        _run_task(task_id, prompt, chat_id, orig_msg_id, bot, history_store=history_store),
        name=f"task-{task_id}",
    )
    _task_sessions.setdefault(chat_id, {})[task_id] = task

    await update.message.reply_text(
        f"⚡ *작업 시작됨* (`{task_id}`)\n\n"
        f"📝 {prompt[:200]}\n\n"
        f"완료되면 이 메시지에 답장으로 결과를 보내드립니다.\n"
        f"취소: `/taskcancel {task_id}`",
        parse_mode="Markdown",
    )


async def taskcancel_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/taskcancel [id] - 실행 중인 작업 취소 (자신의 작업만)"""
    if not await _check_allowed(update, ctx):
        return

    chat_id = update.effective_chat.id
    args = ctx.args or []
    user_tasks = _task_sessions.get(chat_id, {})

    if not args:
        active = [tid for tid, t in user_tasks.items() if not t.done()]
        if not active:
            await update.message.reply_text("ℹ️ 실행 중인 작업이 없습니다.")
            return
        for tid in active:
            user_tasks[tid].cancel()
        await update.message.reply_text(
            f"🚫 {len(active)}개 작업 취소됨: {', '.join(f'`{t}`' for t in active)}",
            parse_mode="Markdown",
        )
        return

    task_id = args[0]
    task = user_tasks.get(task_id)
    if task and not task.done():
        task.cancel()
        await update.message.reply_text(f"🚫 취소 요청됨: `{task_id}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ 작업 없음 또는 이미 완료: `{task_id}`", parse_mode="Markdown")


async def taskstatus_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/taskstatus - 실행 중인 작업 목록 (자신의 작업만)"""
    if not await _check_allowed(update, ctx):
        return

    chat_id = update.effective_chat.id
    user_tasks = _task_sessions.get(chat_id, {})
    active = [(tid, t) for tid, t in user_tasks.items() if not t.done()]

    if not active:
        await update.message.reply_text("📭 실행 중인 작업이 없습니다.")
        return

    lines = [f"⚡ *실행 중인 작업 {len(active)}개*\n"]
    for tid, _ in active:
        lines.append(f"• `{tid}` - 실행 중")
    lines.append(f"\n취소: `/taskcancel <id>`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def clean_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """대화 이력 및 Claude 세션 캐시 전체 초기화"""
    if not await _check_allowed(update, ctx):
        return
    store: ChatHistoryStore | None = ctx.bot_data.get("history_store")
    if store:
        await store.clear()
    await session_mod.new_session()
    await update.message.reply_text("🧹 대화 이력과 세션 캐시를 초기화했습니다.")


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
