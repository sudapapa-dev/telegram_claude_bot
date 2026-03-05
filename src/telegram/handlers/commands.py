from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

from src.shared import ai_session as session_mod
from src.shared.models import AIEngine

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
        "*telegram\\_claude\\_bot*\n\n"
        "메시지를 입력하면 AI가 응답합니다\\.\n\n"
        "💬 *이름 세션*\n"
        "/new \\[이름\\] \\- 새 대화 시작 또는 이름 세션 생성\n"
        "/open \\<이름\\> \\[디렉토리\\] \\- 3개 엔진 세션 동시 생성\n"
        "/open\\_claude \\<이름\\> \\- 🟣 Claude 세션 생성\n"
        "/open\\_gemini \\<이름\\> \\- 💎 Gemini 세션 생성\n"
        "/open\\_gpt \\<이름\\> \\- 🤖 GPT 세션 생성\n"
        "/close \\[이름\\] \\- 해당 이름 전체 엔진 종료 \\(@이름으로 엔진 지정 가능\\)\n"
        "/close\\_claude \\[이름\\] \\- 🟣 Claude 세션 종료 \\(이름 없으면 전체\\)\n"
        "/close\\_gemini \\[이름\\] \\- 💎 Gemini 세션 종료 \\(이름 없으면 전체\\)\n"
        "/close\\_gpt \\[이름\\] \\- 🤖 GPT 세션 종료 \\(이름 없으면 전체\\)\n"
        "/close\\_all \\- 모든 세션 종료\n\n"
        "📨 *메시지 라우팅*\n"
        "`@이름 메시지` \\- 🟣 Claude 세션\n"
        "`@@이름 메시지` \\- 💎 Gemini 세션\n"
        "`@@@이름 메시지` \\- 🤖 GPT 세션\n\n"
        "📋 *세션 목록*\n"
        "`@` \\- Claude 세션 목록\n"
        "`@@` \\- Gemini 세션 목록\n"
        "`@@@` \\- GPT 세션 목록\n"
        "`@@@@` \\- 전체 세션 목록\n\n"
        "⚙️ *시스템*\n"
        "/job \\- 처리 중/대기 중 작업 목록\n"
        "/clean \\- 대화 이력 및 캐시 초기화\n"
        "/status \\- 시스템 상태\n"
        "/history \\- 대화 이력\n"
        "/wol \\[이름\\|MAC\\] \\- Wake on LAN 매직 패킷 전송\n\n"
        "🔐 *인증*\n"
        "/login codex \\- Codex \\(ChatGPT\\) OAuth 인증\n"
        "/logout codex \\- Codex 인증 토큰 삭제\n"
        "/login gemini \\<KEY\\> \\- Gemini API 키 등록\n"
        "/logout gemini \\- Gemini API 키 삭제"
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

    # 엔진별 세션 수
    claude_cnt = sum(1 for s in sessions if s.engine == AIEngine.CLAUDE)
    gemini_cnt = sum(1 for s in sessions if s.engine == AIEngine.GEMINI)
    codex_cnt = sum(1 for s in sessions if s.engine == AIEngine.CODEX)

    default_session = manager.default_session if manager else None
    if default_session:
        engine_icon = ENGINE_LABELS.get(default_session.engine, "")
        default_name = f"{engine_icon} {default_session.display_name}"
    else:
        default_name = "없음"

    text = (
        f"📊 *시스템 상태*\n\n"
        f"세션: {len(sessions)}개\n"
        f"  🟣 Claude: {claude_cnt}\n"
        f"  💎 Gemini: {gemini_cnt}\n"
        f"  🤖 GPT: {codex_cnt}\n\n"
        f"  🟢 대기: {idle}\n"
        f"  🟡 처리중: {busy}\n"
        f"  🔴 종료: {dead}\n\n"
        f"기본 세션: {default_name}"
    )
    await update.message.reply_text(text)



async def new_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int | None:
    """/new [name] - 새 대화 시작 또는 이름 세션 생성"""
    if not await _check_allowed(update, ctx):
        return None

    manager: NamedSessionManager | None = ctx.bot_data.get("named_session_manager")

    args = ctx.args or []
    if not args:
        # 인수 없음 → 기본 세션 재생성
        if not manager:
            await update.message.reply_text("❌ 세션 관리자가 초기화되지 않았습니다.")
            return None
        default_name: str = ctx.bot_data.get("default_session_name", "default")
        # 기존 세션이 있으면 먼저 삭제
        existing = manager.get(default_name, engine=AIEngine.CLAUDE)
        if existing is not None:
            await manager.delete(default_name, engine=AIEngine.CLAUDE)
        session = await manager.create(default_name, engine=AIEngine.CLAUDE)
        await manager.set_default(default_name, engine=AIEngine.CLAUDE)
        await update.message.reply_text(
            f"✅ 기본 세션 *'{session.display_name}'* 을 새로 시작했습니다.",
            parse_mode="Markdown",
        )
        return None

    # 이름 세션 생성 - 첫 인자만 이름 (공백 불가)
    name = args[0].strip()
    if not name:
        await update.message.reply_text("❌ 세션 이름을 입력해주세요.")
        return None

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



ENGINE_LABELS = {
    AIEngine.CLAUDE: "🟣 Claude",
    AIEngine.GEMINI: "💎 Gemini",
    AIEngine.CODEX: "🤖 GPT",
}

_ALL_ENGINES = [AIEngine.CLAUDE, AIEngine.GEMINI, AIEngine.CODEX]


async def _do_open(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    engines: list[AIEngine],
    cmd: str,
) -> None:
    """open 계열 명령 공통 로직."""
    if not await _check_allowed(update, ctx):
        return

    args = ctx.args or []
    if not args:
        engine_hint = " + ".join(ENGINE_LABELS[e] for e in engines)
        await update.message.reply_text(
            f"사용법: `/{cmd} <이름> [디렉토리]`\n\n"
            f"생성 대상: {engine_hint}",
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

    results: list[str] = []
    errors: list[str] = []
    for engine in engines:
        try:
            session = await manager.create(name, working_dir, engine=engine)
            label = ENGINE_LABELS.get(engine, engine.value)
            results.append(f"✅ {label} *'{session.display_name}'*\n   📁 `{session.working_dir}`")
        except ValueError as e:
            errors.append(f"❌ {ENGINE_LABELS.get(engine, engine.value)}: {e}")

    parts = results + errors
    header = f"세션 생성 결과 ({len(results)}/{len(engines)}):\n\n" if len(engines) > 1 else ""
    await update.message.reply_text(header + "\n\n".join(parts), parse_mode="Markdown")


async def open_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/open <name> [directory] - 3개 엔진(Claude+Gemini+GPT) 세션 동시 생성."""
    await _do_open(update, ctx, _ALL_ENGINES, "open")


async def open_claude_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/open_claude <name> [directory] - Claude 세션 생성."""
    await _do_open(update, ctx, [AIEngine.CLAUDE], "open_claude")


async def open_gemini_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/open_gemini <name> [directory] - Gemini 세션 생성."""
    await _do_open(update, ctx, [AIEngine.GEMINI], "open_gemini")


async def open_gpt_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/open_gpt <name> [directory] - GPT(Codex) 세션 생성."""
    await _do_open(update, ctx, [AIEngine.CODEX], "open_gpt")


async def _show_session_list(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    engine_filter: AIEngine | None = None,
) -> None:
    """세션 목록 표시.

    Args:
        engine_filter: None이면 전체, 지정 시 해당 엔진만 표시.
    """
    manager: NamedSessionManager | None = ctx.bot_data.get("named_session_manager")
    if not manager:
        await update.message.reply_text("❌ 세션 관리자가 초기화되지 않았습니다.")
        return

    sessions = manager.list_by_engine(engine_filter)
    if not sessions:
        filter_label = ENGINE_LABELS.get(engine_filter, "전체") if engine_filter else "전체"
        await update.message.reply_text(
            f"생성된 {filter_label} 세션이 없습니다.\n\n"
            "세션 생성:\n"
            "- `/open <이름>` - 🟣 Claude\n"
            "- `/open //<이름>` - 💎 Gemini\n"
            "- `/open ///<이름>` - 🤖 GPT\n"
            "- `/open ////<이름>` - 전체 동시 생성",
            parse_mode="Markdown",
        )
        return

    status_labels = {"idle": "idle", "busy": "busy", "dead": "dead"}
    status_icons = {"idle": "🟢", "busy": "🟡", "dead": "🔴"}
    engine_icons = {
        AIEngine.CLAUDE: "🟣",
        AIEngine.GEMINI: "💎",
        AIEngine.CODEX: "🤖",
    }
    default_session = manager.default_session

    # 컬럼 너비 계산
    name_w = max(len("세션"), max(len(s.display_name) + (1 if default_session and default_session.name == s.name else 0) for s in sessions))
    eng_w  = max(len("엔진"), 6)
    stat_w = max(len("상태"), max(len(status_labels.get(s.status.value, s.status.value)) for s in sessions))
    dir_w  = max(len("디렉토리"), max(len(s.working_dir) for s in sessions))

    div = f"+{'-'*(name_w+2)}+{'-'*(eng_w+2)}+{'-'*(stat_w+2)}+{'-'*(dir_w+2)}+"
    hdr = f"| {'세션':{name_w}} | {'엔진':{eng_w}} | {'상태':{stat_w}} | {'디렉토리':{dir_w}} |"

    table_rows = [div, hdr, div]
    for s in sessions:
        icon = status_icons.get(s.status.value, "⚪")
        stat = status_labels.get(s.status.value, s.status.value)
        is_default = default_session and default_session.name == s.name
        name_cell = s.display_name + ("*" if is_default else "")
        eng_icon = engine_icons.get(s.engine, "")
        eng_label = s.engine.value
        table_rows.append(
            f"| {name_cell:{name_w}} | {eng_icon}{eng_label:{eng_w}} | {icon}{stat:{stat_w}} | {s.working_dir:{dir_w}} |"
        )
    table_rows.append(div)

    filter_label = ENGINE_LABELS.get(engine_filter, "전체") if engine_filter else "전체"
    note = "* 기본 세션" if default_session and any(s.name == default_session.name for s in sessions) else ""
    msg_parts = [
        f"*{filter_label} 세션 목록* ({len(sessions)}개)",
        f"```\n{chr(10).join(table_rows)}\n```",
    ]
    if note:
        msg_parts.append(f"_{note}_")
    # 사용법 표시
    usage_lines = [
        "`@이름 메시지` → Claude",
        "`@@이름 메시지` → Gemini",
        "`@@@이름 메시지` → GPT",
    ]
    msg_parts.append(" | ".join(usage_lines))
    await update.message.reply_text("\n".join(msg_parts), parse_mode="Markdown")


_ENGINE_ARG_MAP: dict[str, AIEngine] = {
    "claude": AIEngine.CLAUDE,
    "gemini": AIEngine.GEMINI,
    "gpt": AIEngine.CODEX,
}


async def session_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/session [claude|gemini|gpt] - 세션 목록 조회."""
    if not await _check_allowed(update, ctx):
        return

    args = ctx.args or []
    if args:
        engine_key = args[0].lower()
        engine = _ENGINE_ARG_MAP.get(engine_key)
        if engine is None:
            await update.message.reply_text(
                f"❌ 알 수 없는 엔진: `{args[0]}`\n사용 가능: claude, gemini, gpt",
                parse_mode="Markdown",
            )
            return
    else:
        engine = None

    await _show_session_list(update, ctx, engine_filter=engine)


async def close_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/close [이름] - 이름 세션 종료.

    이름만 입력 시 해당 이름의 모든 엔진 세션 종료.
    @이름/@@이름/@@@이름 접두사로 특정 엔진만 종료 가능.
    인수 없이 호출 시 기본(전역) 세션 초기화.
    """
    if not await _check_allowed(update, ctx):
        return

    manager: "NamedSessionManager | None" = ctx.bot_data.get("named_session_manager")
    if not manager:
        await update.message.reply_text("❌ 세션 관리자가 초기화되지 않았습니다.")
        return

    args = ctx.args or []
    if not args:
        # 인수 없이 호출 → 기본 세션 종료
        default = manager.default_session
        if default is None:
            await update.message.reply_text("ℹ️ 지정된 기본 세션이 없습니다.")
            return
        await manager.delete(default.display_name, engine=default.engine)
        await update.message.reply_text(
            f"✅ 기본 세션 *'{default.display_name}'* 을 종료했습니다.", parse_mode="Markdown"
        )
        return

    raw = " ".join(args).strip()
    clean_name, engine = manager.parse_name_engine(raw)

    if engine is not None:
        # 엔진 접두사 지정 → 특정 엔진 세션만 종료
        deleted = await manager.delete(clean_name, engine=engine)
        if deleted:
            label = ENGINE_LABELS.get(engine, engine.value)
            await update.message.reply_text(
                f"✅ *{label} | {clean_name}* 세션이 종료되었습니다.", parse_mode="Markdown"
            )
        else:
            label = ENGINE_LABELS.get(engine, engine.value)
            await update.message.reply_text(
                f"❌ '{label} | {clean_name}' 세션을 찾을 수 없습니다."
            )
    else:
        # 엔진 접두사 없음 → 해당 이름의 모든 엔진 세션 종료
        count = await manager.delete_all_by_name(clean_name)
        if count > 0:
            await update.message.reply_text(
                f"✅ *'{clean_name}'* 세션 {count}개 종료되었습니다.", parse_mode="Markdown"
            )
        else:
            sessions = manager.list_all()
            names = ", ".join(f"`{s.display_name}`" for s in sessions) if sessions else "없음"
            await update.message.reply_text(
                f"❌ '{raw}' 세션을 찾을 수 없습니다.\n\n"
                f"등록된 세션: {names}",
                parse_mode="Markdown",
            )


async def _do_close(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    engine: AIEngine,
) -> None:
    """close_claude/gemini/gpt 공통 로직."""
    if not await _check_allowed(update, ctx):
        return

    manager: "NamedSessionManager | None" = ctx.bot_data.get("named_session_manager")
    if not manager:
        await update.message.reply_text("❌ 세션 관리자가 초기화되지 않았습니다.")
        return

    label = ENGINE_LABELS.get(engine, engine.value)
    args = ctx.args or []

    if not args:
        # 이름 없이 호출 → 해당 엔진 전체 종료
        count = await manager.delete_by_engine(engine)
        if count > 0:
            await update.message.reply_text(f"✅ {label} 세션 {count}개를 모두 종료했습니다.")
        else:
            await update.message.reply_text(f"ℹ️ {label} 세션이 없습니다.")
        return

    name = " ".join(args).strip()
    deleted = await manager.delete(name, engine=engine)
    if deleted:
        await update.message.reply_text(
            f"✅ *{label} | {name}* 세션이 종료되었습니다.", parse_mode="Markdown"
        )
    else:
        sessions = manager.list_by_engine(engine)
        names = ", ".join(f"`{s.display_name}`" for s in sessions) if sessions else "없음"
        await update.message.reply_text(
            f"❌ '{name}' {label} 세션을 찾을 수 없습니다.\n\n"
            f"등록된 {label} 세션: {names}",
            parse_mode="Markdown",
        )


async def close_claude_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/close_claude [이름] - Claude 세션 종료. 이름 없으면 전체 종료."""
    await _do_close(update, ctx, AIEngine.CLAUDE)


async def close_gemini_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/close_gemini [이름] - Gemini 세션 종료. 이름 없으면 전체 종료."""
    await _do_close(update, ctx, AIEngine.GEMINI)


async def close_gpt_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/close_gpt [이름] - GPT(Codex) 세션 종료. 이름 없으면 전체 종료."""
    await _do_close(update, ctx, AIEngine.CODEX)




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
            # prefix 라우팅 시도 (caption 기준)
            target_full = img_manager.parse_address_full(caption) if img_manager else None
            if target_full:
                session_name, content, engine = target_full
                img_prompt = f"[이미지 첨부됨: image.jpg]\n{content}"
                reply = await img_manager.ask(session_name, img_prompt, engine=engine)
                engine_label = ENGINE_LABELS.get(engine, engine.value)
                sender = f"{engine_label} | {session_name}"
                ns = img_manager.get(session_name, engine=engine)
                if store and ns:
                    _kw = dict(session_name=ns.display_name, session_uid=ns.session_uid, session_id=ns.claude_session_id)
                    await store.append(role="user", content=img_prompt, **_kw)
                    await store.append(role="assistant", content=reply, **_kw)
            elif img_manager and img_manager.default_session is not None:
                default = img_manager.default_session
                img_prompt = f"[이미지 첨부됨: image.jpg]\n{caption or ''}"
                reply = await img_manager.ask(default.display_name, img_prompt, engine=default.engine)
                engine_label = ENGINE_LABELS.get(default.engine, default.engine.value)
                sender = f"{engine_label} | {default.display_name}"
                if store:
                    _kw = dict(session_name=default.display_name, session_uid=default.session_uid, session_id=default.claude_session_id)
                    await store.append(role="user", content=img_prompt, **_kw)
                    await store.append(role="assistant", content=reply, **_kw)
            else:
                sessions = img_manager.list_all() if img_manager else []
                if sessions:
                    names = "\n".join(f"  • `@{s.display_name}` ({ENGINE_LABELS.get(s.engine, s.engine.value)})" for s in sessions)
                    reply = f"❌ 기본 세션이 지정되지 않았습니다.\n\n등록된 세션:\n{names}\n\n사용법: `@세션이름 메시지`"
                else:
                    reply = "❌ 활성화된 세션이 없습니다.\n`/open <이름>` 으로 세션을 생성하세요."
            await _delete_ack()
            await _send_reply(reply, session_name=sender)
        except Exception as e:
            logger.exception("AI CLI 오류 (이미지)")
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
        # 0. @@@@이름 브로드캐스트 (해당 이름의 모든 엔진 세션에 동시 전달)
        broadcast = manager.parse_broadcast(prompt) if manager else None
        if broadcast:
            bcast_name, bcast_content = broadcast
            sessions_for_name = [s for s in manager.list_all() if s.display_name.lower() == bcast_name.lower()]
            tasks = [manager.ask(s.display_name, bcast_content, engine=s.engine) for s in sessions_for_name]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            parts = []
            for s, result in zip(sessions_for_name, results):
                label = f"{ENGINE_LABELS.get(s.engine, s.engine.value)} | {s.display_name}"
                if isinstance(result, Exception):
                    parts.append(f"[{label}]\n❌ 오류: {result}")
                else:
                    parts.append(f"[{label}]\n{result}")
            await _delete_ack()
            for part in parts:
                await _send_reply(part)
            typing_task.cancel()
            return

        # 1. prefix 라우팅 시도 (@=Claude, @@=Gemini, @@@=GPT)
        target_full = manager.parse_address_full(prompt) if manager else None
        sender: str | None = None
        if target_full:
            session_name, content, engine = target_full
            try:
                reply = await manager.ask(session_name, content, engine=engine)
                engine_label = ENGINE_LABELS.get(engine, engine.value)
                sender = f"{engine_label} | {session_name}"
                # named session 이력 저장
                ns = manager.get(session_name, engine=engine)
                if store and ns:
                    _kw = dict(session_name=ns.display_name, session_uid=ns.session_uid, session_id=ns.claude_session_id)
                    await store.append(role="user", content=content, **_kw)
                    await store.append(role="assistant", content=reply, **_kw)
            except NamedSessionNotFoundError:
                reply = f"❌ '{session_name}' 세션을 찾을 수 없습니다."
        elif manager and manager.default_session is not None:
            # 2. default session → 해당 세션으로 전달
            default = manager.default_session
            try:
                reply = await manager.ask(default.display_name, prompt, engine=default.engine)
                engine_label = ENGINE_LABELS.get(default.engine, default.engine.value)
                sender = f"{engine_label} | {default.display_name}"
                if store:
                    _kw = dict(session_name=default.display_name, session_uid=default.session_uid, session_id=default.claude_session_id)
                    await store.append(role="user", content=prompt, **_kw)
                    await store.append(role="assistant", content=reply, **_kw)
            except NamedSessionNotFoundError:
                await manager.clear_default()
                reply = "❌ 기본 세션이 종료되었습니다.\n`/open <이름>` 으로 세션을 다시 생성하세요."
        else:
            # 3. 기본 세션 없음 → 오류 안내
            sessions = manager.list_all() if manager else []
            if sessions:
                names = "\n".join(f"  • `@{s.display_name}` ({ENGINE_LABELS.get(s.engine, s.engine.value)})" for s in sessions)
                reply = f"❌ 기본 세션이 지정되지 않았습니다.\n\n등록된 세션:\n{names}\n\n사용법: `@세션이름 메시지`"
            else:
                reply = "❌ 활성화된 세션이 없습니다.\n`/open <이름>` 으로 세션을 생성하세요."

        await _delete_ack()
        await _send_reply(reply, session_name=sender)
    except Exception as e:
        logger.exception("AI CLI 오류")
        await _delete_ack()
        await bot.send_message(chat_id=chat_id, text=f"❌ 오류: {e}", reply_to_message_id=message_id)
    finally:
        typing_task.cancel()


async def close_all_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/close_all - 모든 이름 세션 종료"""
    if not await _check_allowed(update, ctx):
        return

    manager: "NamedSessionManager | None" = ctx.bot_data.get("named_session_manager")
    if not manager:
        await update.message.reply_text("❌ 세션 관리자가 초기화되지 않았습니다.")
        return

    count = await manager.delete_all()
    await update.message.reply_text(f"🗑️ 세션 {count}개를 모두 종료했습니다.")


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


async def login_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/login <대상> — OAuth Device Code 인증.

    /login codex   — Codex (ChatGPT) 인증 시작
    /login status  — 진행 중인 인증 상태 확인
    """
    if not await _check_allowed(update, ctx):
        return

    from src.shared.codex_auth import (
        cancel_device_auth,
        is_auth_running,
        start_device_auth,
    )

    args = ctx.args or []
    target = args[0].lower() if args else ""
    chat_id = _chat_id(update)
    bot = ctx.bot

    if target == "codex":
        if is_auth_running():
            await update.message.reply_text(
                "⚠️ 이미 Codex 인증이 진행 중입니다.\n취소하려면 `/login cancel`",
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text("🔐 Codex 인증을 시작합니다...")

        async def on_code(url: str, code: str) -> None:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "🔑 *Codex 인증 코드*\n\n"
                    f"1\\. 아래 링크에서 ChatGPT 계정으로 로그인하세요:\n"
                    f"{url}\n\n"
                    f"2\\. 이 코드를 입력하세요:\n"
                    f"`{code}`\n\n"
                    "_코드는 15분 후 만료됩니다\\._"
                ),
                parse_mode="MarkdownV2",
            )

        async def on_done() -> None:
            await bot.send_message(
                chat_id=chat_id,
                text="✅ Codex 인증이 완료되었습니다! `codex` 명령을 사용할 수 있습니다.",
                parse_mode="Markdown",
            )

        async def on_error(msg: str) -> None:
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ Codex 인증 실패: {msg}",
            )

        try:
            await start_device_auth(on_code, on_done, on_error)
        except RuntimeError as e:
            await update.message.reply_text(f"❌ {e}")

    elif target == "status":
        running = is_auth_running()
        if running:
            await update.message.reply_text(
                "🔄 Codex 인증 진행 중입니다.\n브라우저에서 코드를 입력해주세요.\n취소: `/login cancel`",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text("ℹ️ 진행 중인 인증이 없습니다.")

    elif target == "cancel":
        cancelled = await cancel_device_auth()
        if cancelled:
            await update.message.reply_text("🛑 Codex 인증을 취소했습니다.")
        else:
            await update.message.reply_text("ℹ️ 진행 중인 인증이 없습니다.")

    elif target == "gemini":
        await login_gemini_command(update, ctx)

    else:
        await update.message.reply_text(
            "사용법:\n"
            "`/login codex` — Codex \\(ChatGPT\\) 인증 시작\n"
            "`/login gemini` — Gemini 인증 설정\n"
            "`/login status` — 인증 진행 상태 확인\n"
            "`/login cancel` — 진행 중인 인증 취소",
            parse_mode="MarkdownV2",
        )


async def logout_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/logout <대상> — 인증 토큰 제거.

    /logout codex  — Codex 인증 토큰 삭제
    """
    if not await _check_allowed(update, ctx):
        return

    args = ctx.args or []
    target = args[0].lower() if args else ""

    if target == "codex":
        import subprocess
        import shutil

        codex = shutil.which("codex")
        if not codex:
            await update.message.reply_text("❌ codex CLI를 찾을 수 없습니다.")
            return

        try:
            result = subprocess.run(
                [codex, "logout"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                await update.message.reply_text("✅ Codex 인증 토큰이 삭제되었습니다.")
            else:
                err = (result.stderr or result.stdout or "알 수 없는 오류").strip()
                await update.message.reply_text(f"❌ 로그아웃 실패: {err}")
        except Exception as e:
            await update.message.reply_text(f"❌ 오류: {e}")

    elif target == "gemini":
        from src.shared.gemini_auth import remove_api_key, cancel_google_auth

        await cancel_google_auth()
        removed = remove_api_key()
        if removed:
            await update.message.reply_text("✅ Gemini API 키가 삭제되었습니다.")
        else:
            await update.message.reply_text("❌ Gemini API 키 삭제에 실패했습니다.")

    else:
        await update.message.reply_text(
            "사용법:\n"
            "`/logout codex` — Codex 인증 토큰 삭제\n"
            "`/logout gemini` — Gemini API 키 삭제",
            parse_mode="Markdown",
        )


async def login_gemini_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/login gemini 서브커맨드 처리.

    /login gemini <API_KEY>  — API 키 직접 등록
    /login gemini google     — Google OAuth 인증 시작
    /login gemini status     — 현재 인증 상태 확인
    /login gemini cancel     — 진행 중인 Google OAuth 취소
    """
    from src.shared.gemini_auth import (
        cancel_google_auth,
        get_auth_status,
        is_oauth_running,
        save_api_key_to_env_file,
        start_google_auth,
    )

    args = ctx.args or []
    # args[0] 은 이미 "gemini" — 실제 서브인수는 args[1:]
    sub_args = args[1:] if len(args) > 1 else []
    sub = sub_args[0].lower() if sub_args else ""
    chat_id = _chat_id(update)
    bot = ctx.bot

    # ── API 키 직접 설정 ──────────────────────────────────────────────────────
    if sub and sub not in ("google", "status", "cancel") :
        # 첫 번째 서브인수가 API 키처럼 보이면 저장
        api_key = sub_args[0].strip()
        if len(api_key) < 10:
            await update.message.reply_text(
                "❌ 유효하지 않은 API 키입니다.\n"
                "사용법: `/login gemini <GEMINI_API_KEY>`",
                parse_mode="Markdown",
            )
            return
        ok = save_api_key_to_env_file(api_key)
        if ok:
            await update.message.reply_text(
                "✅ Gemini API 키가 저장되었습니다.\n"
                f"키: `{api_key[:8]}...`",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text("❌ API 키 저장에 실패했습니다.")
        return

    # ── 상태 확인 ──────────────────────────────────────────────────────────────
    if sub == "status":
        status = get_auth_status()
        lines = ["🔍 *Gemini 인증 상태*\n"]
        if status["api_key_set"]:
            lines.append(f"✅ API 키: `{status['api_key_preview']}`")
        else:
            lines.append("❌ API 키: 미설정")
        lines.append(f"🔄 Google OAuth 진행 중: {'예' if status['oauth_running'] else '아니오'}")
        lines.append(f"📍 gemini CLI: `{status['gemini_path'] or '미설치'}`")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # ── OAuth 취소 ─────────────────────────────────────────────────────────────
    if sub == "cancel":
        cancelled = await cancel_google_auth()
        if cancelled:
            await update.message.reply_text("🛑 Gemini Google 인증을 취소했습니다.")
        else:
            await update.message.reply_text("ℹ️ 진행 중인 인증이 없습니다.")
        return

    # ── Google OAuth ───────────────────────────────────────────────────────────
    if sub == "google":
        if is_oauth_running():
            await update.message.reply_text(
                "⚠️ 이미 Google 인증이 진행 중입니다.\n취소: `/login gemini cancel`",
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text(
            "🔐 Gemini Google OAuth 인증을 시작합니다...\n"
            "_⚠️ 서버 환경에서는 콜백 수신이 제한될 수 있습니다._\n"
            "API 키 방식 권장: `/login gemini <GEMINI_API_KEY>`",
            parse_mode="Markdown",
        )

        async def on_url(url: str) -> None:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "🔑 *Gemini Google 인증*\n\n"
                    "아래 링크에서 Google 계정으로 로그인하세요:\n"
                    f"{url}"
                ),
                parse_mode="Markdown",
            )

        async def on_done() -> None:
            await bot.send_message(
                chat_id=chat_id,
                text="✅ Gemini Google 인증이 완료되었습니다!",
            )

        async def on_error(msg: str) -> None:
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ Gemini 인증 실패: {msg}",
            )

        try:
            await start_google_auth(on_url, on_done, on_error)
        except RuntimeError as e:
            await update.message.reply_text(f"❌ {e}")
        return

    # ── 기본: 사용법 안내 ──────────────────────────────────────────────────────
    await update.message.reply_text(
        "🔐 *Gemini 인증 방법*\n\n"
        "*1\\. API 키 방식 \\(권장\\)*\n"
        "`/login gemini <GEMINI_API_KEY>`\n"
        "무료 티어: 60 req/min, 1,000 req/day\n"
        "키 발급: https://aistudio\\.google\\.com/apikey\n\n"
        "*2\\. Google OAuth*\n"
        "`/login gemini google`\n\n"
        "*상태/취소*\n"
        "`/login gemini status`\n"
        "`/login gemini cancel`",
        parse_mode="MarkdownV2",
    )


def _load_wol_devices() -> dict:
    """프로젝트 루트의 .wol.json에서 기기 목록 로드."""
    import json
    import sys

    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / ".wol.json")
    else:
        candidates.append(Path(__file__).resolve().parent.parent.parent / ".wol.json")
    candidates.append(Path.cwd() / ".wol.json")

    for p in candidates:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return data.get("devices", {})
            except Exception:
                pass
    return {}


async def wol_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/wol - Wake on LAN 매직 패킷 전송.

    /wol                - .wol.json 기기 목록 표시
    /wol <이름>          - .wol.json에 저장된 기기로 전송 (예: /wol nas)
    /wol <MAC>          - 직접 MAC 주소로 전송 (예: /wol 58-11-22-BB-F9-5F)
    /wol <MAC> <브로드캐스트> - 브로드캐스트 주소 지정
    """
    if not await _check_allowed(update, ctx):
        return

    import socket

    args = ctx.args or []
    devices = _load_wol_devices()

    # 인자 없음 → 기기 목록 표시
    if not args:
        if devices:
            lines = ["📋 *저장된 WOL 기기 목록*\n"]
            for name, info in devices.items():
                desc = info.get("description", "")
                mac = info.get("mac", "")
                lines.append(f"• `{name}` — {mac}" + (f" ({desc})" if desc else ""))
            lines.append(f"\n사용법: `/wol <이름>` 또는 `/wol <MAC>`")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        else:
            await update.message.reply_text(
                "❌ 저장된 기기가 없습니다.\n"
                "`.wol.json` 파일을 프로젝트 루트에 생성하거나\n"
                "직접 MAC 주소를 입력하세요.\n\n"
                "예: `/wol 58-11-22-BB-F9-5F`",
                parse_mode="Markdown",
            )
        return

    target = args[0]
    broadcast = args[1] if len(args) > 1 else None

    # 이름으로 기기 조회
    device = devices.get(target.lower())
    if device:
        mac_str = device.get("mac", "")
        broadcast = broadcast or device.get("broadcast", "255.255.255.255")
        label = f"{target} ({device.get('description', mac_str)})"
    else:
        # 직접 MAC 주소 입력
        mac_str = target
        broadcast = broadcast or os.environ.get("WOL_BROADCAST", "255.255.255.255")
        label = mac_str

    # MAC 파싱 (구분자 제거)
    mac_clean = mac_str.replace("-", "").replace(":", "").upper()
    if len(mac_clean) != 12 or not all(c in "0123456789ABCDEF" for c in mac_clean):
        hint = f"\n저장된 기기: {', '.join(f'`{n}`' for n in devices)}" if devices else ""
        await update.message.reply_text(
            f"❌ 알 수 없는 이름 또는 잘못된 MAC 형식: `{target}`{hint}",
            parse_mode="Markdown",
        )
        return

    mac_bytes = bytes.fromhex(mac_clean)
    magic = b'\xff' * 6 + mac_bytes * 16  # 102 bytes

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic, (broadcast, 9))

        await update.message.reply_text(
            f"✅ WOL 매직 패킷 전송 완료!\n"
            f"대상: `{label}`\n"
            f"MAC: `{mac_str.upper()}`\n"
            f"브로드캐스트: `{broadcast}`",
            parse_mode="Markdown",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ 전송 실패: {e}")

