"""telegram_claude_bot - 진입점"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

import structlog

from src.shared import ai_session
from src.shared.chat_history import ChatHistoryStore
from src.shared.config import Settings
from src.shared.database import Database
from src.telegram.bot import TelegramClaudeBot


def _inject_mcp_servers(notion_token: str) -> None:
    """NOTION_TOKEN이 있으면 ~/.claude.json에 Notion MCP 서버 설정을 자동 주입.

    기존 mcpServers의 다른 항목은 보존하고 notion 항목만 추가/갱신한다.
    토큰이 비어있으면 아무 작업도 하지 않는다.
    """
    log = logging.getLogger("telegram_claude_bot")
    if not notion_token:
        return

    claude_json_path = Path.home() / ".claude.json"

    # 기존 설정 읽기
    config: dict = {}
    if claude_json_path.exists():
        try:
            config = json.loads(claude_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning("~/.claude.json 파싱 실패 — 새로 생성합니다")
            config = {}

    # Notion MCP 서버 설정
    mcp_servers = config.setdefault("mcpServers", {})
    mcp_servers["notion"] = {
        "command": "npx",
        "args": ["-y", "@notionhq/notion-mcp-server"],
        "env": {
            "OPENAPI_MCP_HEADERS": json.dumps({
                "Authorization": f"Bearer {notion_token}",
                "Notion-Version": "2022-06-28",
            }),
        },
    }

    # 저장
    try:
        claude_json_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        log.info("Notion MCP 설정 주입 완료: %s", claude_json_path)
    except OSError:
        log.exception("~/.claude.json 쓰기 실패")


def setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO, stream=sys.stdout,
    )
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )


async def _async_main(stop_event: asyncio.Event) -> None:
    """봇 및 오케스트레이터 실행 (asyncio 루프 안)"""
    log = logging.getLogger("telegram_claude_bot")

    settings = Settings()

    # MCP 서버 자동 설정 (NOTION_TOKEN이 있으면 ~/.claude.json에 주입)
    _inject_mcp_servers(notion_token=settings.notion_token)

    db = Database(settings.database_path)
    await db.initialize()

    # 데이터 디렉토리 (DB와 동일 위치 기준)
    data_dir = Path(settings.database_path).parent

    # AI 세션 매니저 초기화
    ai_session.init_default(
        claude_path=settings.claude_code_path,
        model=settings.default_model or None,
        data_dir=data_dir,
        system_prompt=settings.system_prompt or "",
    )

    # 대화 이력 스토어 초기화 (Docker: /app/data, 로컬: DB와 같은 디렉토리)
    history_store = ChatHistoryStore(json_path=data_dir / "chat_history.json", db=db)
    await history_store.load()
    ai_session.set_history_store(history_store)

    settings.warn_if_open_access()

    bot = TelegramClaudeBot(
        token=settings.telegram_bot_token.get_secret_value(),
        allowed_users=settings.telegram_chat_id,
        history_store=history_store,
        default_session_name=settings.default_session_name or None,
        db=db,
    )
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows

    log.info("telegram_claude_bot 시작")
    await bot.run()

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        log.info("종료 중...")
        await bot.stop()
        await ai_session.stop()
        await db.close()
        log.info("종료 완료")


def _run_async(stop_event: asyncio.Event) -> None:
    """별도 스레드에서 asyncio 루프 실행"""
    asyncio.run(_async_main(stop_event))


def entry() -> None:
    """exe 및 스크립트 진입점 — 트레이 없이 asyncio 직접 실행 (Linux/Docker 호환)"""
    import os
    if getattr(sys, "frozen", False):
        os.chdir(os.path.dirname(sys.executable))

    setup_logging()
    log = logging.getLogger("telegram_claude_bot")
    log.info("telegram_claude_bot 시작 (트레이 없음 모드)")

    try:
        asyncio.run(_async_main(asyncio.Event()))
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt — 종료")


if __name__ == "__main__":
    entry()
