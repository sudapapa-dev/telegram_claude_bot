"""Claude Control Tower - 진입점"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

import structlog

from src.orchestrator.manager import InstanceManager
from src.shared import ai_session
from src.shared.chat_history import ChatHistoryStore
from src.shared.config import Settings
from src.shared.database import Database
from src.shared.events import EventBus
from src.telegram.bot import ControlTowerBot


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
    log = logging.getLogger("controltower")

    settings = Settings()
    event_bus = EventBus()
    db = Database(settings.database_path)
    await db.initialize()

    # 실행파일/스크립트 기준 경로
    base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent.parent

    # AI 세션 매니저 초기화 (Claude / Gemini)
    scripts_dir = base_dir / "scripts"
    ai_session.init_default(
        claude_path=settings.claude_code_path,
        model=settings.default_model or None,
        working_dir=settings.claude_workspace or None,
        scripts_dir=str(scripts_dir) if scripts_dir.exists() else None,
    )

    # 대화 이력 스토어 초기화
    history_store = ChatHistoryStore(json_path=base_dir / "chat_history.json", db=db)
    await history_store.load()
    ai_session.set_history_store(history_store)

    orchestrator = InstanceManager(
        db=db, event_bus=event_bus,
        claude_path=settings.claude_code_path,
        max_concurrent=settings.allowed_users,
    )
    await orchestrator.start()

    bot = ControlTowerBot(
        token=settings.telegram_bot_token,
        orchestrator=orchestrator,
        allowed_users=settings.telegram_chat_id,
        history_store=history_store,
    )
    bot.setup_notifications(event_bus)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows

    log.info("Claude Control Tower 시작")
    await bot.run()

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        log.info("종료 중...")
        await bot.stop()
        await orchestrator.stop()
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
    log = logging.getLogger("controltower")
    log.info("Claude Control Tower 시작 (트레이 없음 모드)")

    try:
        asyncio.run(_async_main(asyncio.Event()))
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt — 종료")


if __name__ == "__main__":
    entry()
