from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

from src.shared import ai_session as session_mod

if TYPE_CHECKING:
    from src.shared.chat_history import ChatHistoryStore
    from src.shared.named_sessions import NamedSessionManager

logger = logging.getLogger(__name__)


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
        "💬 *이름 세션*\n"
        "/new \\[이름\\] \\- 새 대화 시작 또는 이름 세션 생성 \\(자동 디렉토리\\)\n"
        "/open \\<이름\\> \\[디렉토리\\] \\- 이름 세션 생성 \\(디렉토리 선택적\\)\n"
        "/close \\[이름\\] \\- 세션 종료 \\(이름 생략 시 기본 세션 초기화\\)\n"
        "/default \\[이름\\] \\- 기본 라우팅 세션 설정/해제\n\n"
        "`@` \\- 세션 목록 조회\n"
        "`@세션이름 메시지` \\- 세션에 메시지 전달\n\n"
        "⚙️ *시스템*\n"
        "/job \\- 처리 중/대기 중 작업 목록\n"
        "/clean \\- 대화 이력 및 캐시 초기화\n"
        "/status \\- 시스템 상태\n"
        "/history \\- 대화 이력"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def status_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_allowed(update, ctx):
        return
    manager: NamedSessionManager | None = ctx.bot_data.get("named_session_manager")
    sessions = manager.list_all() if manager else []
    idle = sum(1 for s in sessions if s.status.value == "idle")
    busy = sum(1 for s in sessions if s.status.value == "busy")
    dead = sum(1 for s in sessions if s.status.value == "dead")
    default_name = (
        manager.default_session.display_name
        if manager and manager.default_session
        else "\uc5c6\uc74c"
    )
    text = (
        f"\U0001f4ca *\uc2dc\uc2a4\ud15c \uc0c1\ud0dc*\n\n"
        f"\uc138\uc158: {len(sessions)}\uac1c\n"
        f"  \U0001f7e2 \ub300\uae30: {idle}\n"
        f"  \U0001f7e1 \ucc98\ub9ac\uc911: {busy}\n"
        f"  \U0001f534 \uc885\ub8cc: {dead}\n\n"
        f"\uae30\ubcf8 \uc138\uc158: {default_name}"
    )
    await update.message.reply_text(text)



async def new_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int | None:
    """/new [name] - 새 대화 시작 또는 이름 세션 생성"""
    if not await _check_allowed(update, ctx):
        return None

    args = ctx.args or []
    if not args:
        # 기본 세션 리셋
        await session_mod.new_session()
        await update.message.reply_text("새 대화를 시작했습니다.")
        return None

    # 이름 세션 생성 - 첫 인자만 이름 (공백 불가)
    name = args[0].strip()
    if not name:
        await update.message.reply_text("❌ 세션 이름을 입력해주세요.")
        return None

    manager: NamedSessionManager | None = ctx.bot_data.get("named_session_manager")
    if not manager:
        await update.message.reply_text("❌ 세션 관리자가 초기화되지 않았습니다.")
        return None

    try:
        session = await manager.create(name)  # working_dir=None → 자동 생성
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}")
        return None
    await update.message.reply_text(
        f"✅ *'{session.display_name}'* 세션 생성 완료!\n"
        f"📁 `{session.working_dir}`\n\n"
        f"`@{session.display_name} 메시지` 형식으로 대화하세요.",
        parse_mode="Markdown",
    )
    return None



async def open_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/open <name> [directory] - 이름 세션을 생성. 디렉토리 미지정 시 자동 생성."""
    if not await _check_allowed(update, ctx):
        return

    args = ctx.args or []
    if not args:
        await update.message.reply_text(
            "사용법: `/open <이름> [디렉토리]`\n"
            "예: `/open 데이빗 C:/project`\n"
            "예: `/open 데이빗` (자동 디렉토리)",
            parse_mode="Markdown",
        )
        return

    name = args[0].strip()
    if not name:
        await update.message.reply_text("❌ 세션 이름을 입력해주세요.")
        return
    working_dir = " ".join(args[1:]) if len(args) > 1 else None

    manager: NamedSessionManager | None = ctx.bot_data.get("named_session_manager")
    if not manager:
        await update.message.reply_text("❌ 세션 관리자가 초기화되지 않았습니다.")
        return

    try:
        session = await manager.create(name, working_dir)
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}")
        return
    await update.message.reply_text(
        f"✅ *'{session.display_name}'* 세션 준비 완료!\n"
        f"📁 `{session.working_dir}`",
        parse_mode="Markdown",
    )


async def _show_session_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """세션 목록 표시 (@ 입력 또는 내부 호출용)"""
    manager: NamedSessionManager | None = ctx.bot_data.get("named_session_manager")
    if not manager:
        await update.message.reply_text("❌ 세션 관리자가 초기화되지 않았습니다.")
        return

    sessions = manager.list_all()
    if not sessions:
        await update.message.reply_text(
            "생성된 이름 세션이 없습니다.\n\n"
            "세션 생성:\n"
            "- `/new <이름>` - 대화형 생성\n"
            "- `/open <이름> <디렉토리>` - 즉시 생성",
            parse_mode="Markdown",
        )
        return

    status_labels = {"idle": "idle", "busy": "busy", "dead": "dead"}
    status_icons = {"idle": "🟢", "busy": "🟡", "dead": "🔴"}
    default_session = manager.default_session

    # 컬럼 너비 계산 (이모지는 고정폭 폰트에서 2칸 차지하므로 아이콘은 별도 처리)
    name_w = max(len("세션 이름"), max(len(s.display_name) + (1 if default_session and default_session.name == s.name else 0) for s in sessions))
    stat_w = max(len("상태"), max(len(status_labels.get(s.status.value, s.status.value)) for s in sessions))
    uid_w  = max(len("세션 UID"), 12)
    dir_w  = max(len("디렉토리"), max(len(s.working_dir) for s in sessions))

    div = f"+{'-'*(name_w+2)}+{'-'*(stat_w+2)}+{'-'*(uid_w+2)}+{'-'*(dir_w+2)}+"
    hdr = f"| {'세션 이름':{name_w}} | {'상태':{stat_w}} | {'세션 UID':{uid_w}} | {'디렉토리':{dir_w}} |"

    table_rows = [div, hdr, div]
    for s in sessions:
        icon = status_icons.get(s.status.value, "⚪")
        stat = status_labels.get(s.status.value, s.status.value)
        is_default = default_session and default_session.name == s.name
        name_cell = s.display_name + ("*" if is_default else "")
        table_rows.append(
            f"| {name_cell:{name_w}} | {icon}{stat:{stat_w}} | {s.session_uid:{uid_w}} | {s.working_dir:{dir_w}} |"
        )
    table_rows.append(div)

    note = "* 기본 세션" if default_session else ""
    msg_parts = [
        f"*이름 세션 목록* ({len(sessions)}개)",
        f"```\n{chr(10).join(table_rows)}\n```",
    ]
    if note:
        msg_parts.append(f"_{note}_")
    msg_parts.append("사용법: `@세션이름 메시지`")
    await update.message.reply_text("\n".join(msg_parts), parse_mode="Markdown")


async def close_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/close <name> - 이름 세션 종료"""
    if not await _check_allowed(update, ctx):
        return

    manager: "NamedSessionManager | None" = ctx.bot_data.get("named_session_manager")
    if not manager:
        await update.message.reply_text("❌ 세션 관리자가 초기화되지 않았습니다.")
        return

    args = ctx.args or []
    if not args:
        # 인수 없이 호출 → 기본 세션(전역) 리셋
        await session_mod.new_session()
        await update.message.reply_text("✅ 기본 세션이 초기화되었습니다.")
        return

    name = " ".join(args).strip()
    deleted = await manager.delete(name)
    if deleted:
        # default session이 삭제된 세션이었으면 자동 해제됨 (default_session property가 None 반환)
        await update.message.reply_text(f"✅ *'{name}'* 세션이 종료되었습니다.", parse_mode="Markdown")
    else:
        sessions = manager.list_all()
        names = ", ".join(f"`{s.display_name}`" for s in sessions) if sessions else "없음"
        await update.message.reply_text(
            f"❌ '{name}' 세션을 찾을 수 없습니다.\n\n"
            f"등록된 세션: {names}",
            parse_mode="Markdown",
        )


async def default_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/default [name] - 기본 라우팅 세션 변경

    /default <이름>  : 이름 없는 메시지를 해당 세션으로 전달
    /default        : .env 기본 세션으로 복원 (이미 기본이면 무시)
    """
    if not await _check_allowed(update, ctx):
        return

    manager: "NamedSessionManager | None" = ctx.bot_data.get("named_session_manager")
    if not manager:
        await update.message.reply_text("❌ 세션 관리자가 초기화되지 않았습니다.")
        return

    from src.shared.named_sessions import NamedSessionNotFoundError

    args = ctx.args or []
    if not args:
        config_default: str | None = ctx.bot_data.get("default_session_name")
        if not config_default:
            await update.message.reply_text(
                "ℹ️ .env에 DEFAULT_SESSION_NAME이 설정되지 않았습니다.\n"
                "사용법: `/default <세션이름>`",
                parse_mode="Markdown",
            )
            return

        # 이미 .env 기본 세션이면 무시
        current = manager.default_session
        if current and current.name == config_default.strip().lower():
            return

        # 다른 세션이 기본이면 → .env 기본 세션으로 복원
        try:
            session = await manager.set_default(config_default)
            await update.message.reply_text(
                f"↩️ 기본 세션 복원: *{session.display_name}*",
                parse_mode="Markdown",
            )
        except NamedSessionNotFoundError:
            await update.message.reply_text(
                f"❌ 기본 세션 '{config_default}'을 찾을 수 없습니다.",
            )
        return

    name = " ".join(args).strip()
    try:
        session = await manager.set_default(name)
        await update.message.reply_text(
            f"✅ 기본 세션: *{session.display_name}*\n"
            f"📁 `{session.working_dir}`\n\n"
            f"이제 이름 없는 메시지가 이 세션으로 전달됩니다.\n"
            f"복원: `/default`",
            parse_mode="Markdown",
        )
    except NamedSessionNotFoundError:
        sessions = manager.list_all()
        names = ", ".join(f"`{s.display_name}`" for s in sessions) if sessions else "없음"
        await update.message.reply_text(
            f"❌ '{name}' 세션을 찾을 수 없습니다.\n\n"
            f"등록된 세션: {names}",
            parse_mode="Markdown",
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
            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks



async def _process_message(
    bot,
    update_data: dict,
    bot_data: dict,
    chat_id: int,
    message_id: int,
    ack_message_id: int | None,
) -> None:
    """실제 Claude 처리 로직 - MessageQueue 워커에서 호출됨."""
    from telegram import Update as TGUpdate

    update = TGUpdate.de_json(update_data, bot)

    async def _delete_ack() -> None:
        if ack_message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=ack_message_id)
            except Exception:
                pass

    async def _send_reply(reply: str, session_name: str | None = None) -> None:
        """응답을 전송 (3000자 초과 시 파일).

        session_name이 있으면 첫 번째 메시지 앞에 '[이름]' 헤더를 붙임.
        """
        if len(reply) > 3000:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8"
            ) as f:
                if session_name:
                    f.write(f"[{session_name}]\n\n")
                f.write(reply)
                tmp_path = f.name
            try:
                with open(tmp_path, "rb") as f:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename="response.md",
                        caption=f"📄 [{session_name}] 응답이 길어 파일로 전송합니다." if session_name else "📄 응답이 길어 파일로 전송합니다.",
                        reply_to_message_id=message_id,
                    )
            finally:
                os.unlink(tmp_path)
        else:
            chunks = _split_message(reply)
            for i, chunk in enumerate(chunks):
                header = f"[{session_name}]\n" if session_name and i == 0 else ""
                await bot.send_message(
                    chat_id=chat_id,
                    text=header + chunk,
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

    store: ChatHistoryStore | None = bot_data.get("history_store")

    # 이미지 메시지 처리
    if update.message and update.message.photo:
        from src.shared.named_sessions import NamedSessionManager, NamedSessionNotFoundError
        photo = update.message.photo[-1]
        photo_file = await bot.get_file(photo.file_id)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        await photo_file.download_to_drive(tmp_path)
        caption = update.message.caption or "이 이미지에 대해 설명해줘"
        prompt = f"[이미지 첨부됨: image.jpg]\n{caption}"

        img_manager: NamedSessionManager | None = bot_data.get("named_session_manager")
        typing_task = asyncio.create_task(keep_typing())
        try:
            sender: str | None = None
            # 이름 prefix 라우팅 시도 (caption 기준)
            target = img_manager.parse_address(caption) if img_manager else None
            if target:
                session_name, content = target
                img_prompt = f"[이미지 첨부됨: image.jpg]\n{content}"
                reply = await img_manager.ask(session_name, img_prompt)
                sender = session_name
                ns = img_manager.get(session_name)
                if store and ns:
                    _kw = dict(session_name=ns.display_name, session_uid=ns.session_uid, session_id=ns.claude_session_id)
                    await store.append(role="user", content=img_prompt, **_kw)
                    await store.append(role="assistant", content=reply, **_kw)
            elif img_manager and img_manager.default_session is not None:
                default = img_manager.default_session
                reply = await img_manager.ask(default.display_name, prompt)
                sender = default.display_name
                if store:
                    _kw = dict(session_name=default.display_name, session_uid=default.session_uid, session_id=default.claude_session_id)
                    await store.append(role="user", content=prompt, **_kw)
                    await store.append(role="assistant", content=reply, **_kw)
            else:
                reply = await session_mod.ask(prompt, save_history=True)
            await _delete_ack()
            await _send_reply(reply, session_name=sender)
        except Exception as e:
            logger.exception("Claude CLI 오류 (이미지)")
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
        await _delete_ack()
        return

    # 이름 기반 세션 라우팅 시도
    from src.shared.named_sessions import NamedSessionManager, NamedSessionNotFoundError
    manager: NamedSessionManager | None = bot_data.get("named_session_manager")

    typing_task = asyncio.create_task(keep_typing())
    try:
        # 1. 이름 prefix 라우팅 시도 ("이름, 내용" / "이름: 내용")
        target = manager.parse_address(prompt) if manager else None
        sender: str | None = None
        if target:
            session_name, content = target
            try:
                reply = await manager.ask(session_name, content)
                sender = session_name
                # named session 이력 저장
                ns = manager.get(session_name)
                if store and ns:
                    _kw = dict(session_name=ns.display_name, session_uid=ns.session_uid, session_id=ns.claude_session_id)
                    await store.append(role="user", content=content, **_kw)
                    await store.append(role="assistant", content=reply, **_kw)
            except NamedSessionNotFoundError:
                reply = f"❌ '{session_name}' 세션을 찾을 수 없습니다. `/session` 으로 세션 목록을 확인하세요."
        elif manager and manager.default_session is not None:
            # 2. default session이 설정된 경우 해당 세션으로 전달
            default = manager.default_session
            try:
                reply = await manager.ask(default.display_name, prompt)
                sender = default.display_name
                # default named session 이력 저장
                if store:
                    _kw = dict(session_name=default.display_name, session_uid=default.session_uid, session_id=default.claude_session_id)
                    await store.append(role="user", content=prompt, **_kw)
                    await store.append(role="assistant", content=reply, **_kw)
            except NamedSessionNotFoundError:
                await manager.clear_default()
                reply = await session_mod.ask(prompt, save_history=True)
        else:
            # 3. 기본 Claude 세션 풀로 전달
            reply = await session_mod.ask(prompt, save_history=True)

        await _delete_ack()
        await _send_reply(reply, session_name=sender)
    except Exception as e:
        logger.exception("Claude CLI 오류")
        await _delete_ack()
        await bot.send_message(chat_id=chat_id, text=f"❌ 오류: {e}", reply_to_message_id=message_id)
    finally:
        typing_task.cancel()


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


