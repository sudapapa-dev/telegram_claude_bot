"""Claude Control Tower - 진입점"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
import threading
from pathlib import Path

import structlog

from src.orchestrator.manager import InstanceManager
from src.shared import claude_session
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

    # 전역 Claude CLI 프로세스 초기화
    scripts_dir = base_dir / "scripts"
    claude_session.init_default(
        claude_path=settings.claude_code_path,
        model=settings.default_model or None,
        working_dir=settings.claude_workspace or None,
        scripts_dir=str(scripts_dir) if scripts_dir.exists() else None,
    )

    # 대화 이력 스토어 초기화
    history_store = ChatHistoryStore(json_path=base_dir / "chat_history.json", db=db)
    await history_store.load()
    claude_session.set_history_store(history_store)

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
        await claude_session.stop()
        await db.close()
        log.info("종료 완료")


def _run_async(stop_event: asyncio.Event) -> None:
    """별도 스레드에서 asyncio 루프 실행"""
    asyncio.run(_async_main(stop_event))


def entry() -> None:
    """exe 및 스크립트 진입점 — 트레이는 메인 스레드, asyncio는 별도 스레드"""
    import os
    if getattr(sys, "frozen", False):
        os.chdir(os.path.dirname(sys.executable))

    setup_logging()
    log = logging.getLogger("controltower")

    # asyncio용 stop_event (스레드 간 공유)
    # pystray.Icon.stop()에서 asyncio stop_event를 set하기 위해 루프를 나중에 연결
    _loop_holder: list[asyncio.AbstractEventLoop] = []
    _stop_holder: list[asyncio.Event] = []

    ready = threading.Event()  # asyncio 루프 준비 완료 신호

    def _async_thread() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        stop_ev = asyncio.Event()
        _loop_holder.append(loop)
        _stop_holder.append(stop_ev)
        ready.set()  # 루프/이벤트 준비 완료
        loop.run_until_complete(_async_main(stop_ev))

    t = threading.Thread(target=_async_thread, daemon=True)
    t.start()

    # 루프/이벤트가 준비될 때까지 대기
    ready.wait(timeout=10)

    # 트레이 아이콘 (메인 스레드에서 실행 — Windows 필수)
    try:
        import pystray
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill=(30, 120, 220, 255))
        draw.text((18, 18), "CT", fill=(255, 255, 255, 255))

        def on_quit(icon, item):
            icon.stop()
            if _loop_holder and _stop_holder:
                _loop_holder[0].call_soon_threadsafe(_stop_holder[0].set)

        menu = pystray.Menu(
            pystray.MenuItem("Claude Control Tower", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("종료", on_quit),
        )
        icon = pystray.Icon("controltower", img, "Claude Control Tower", menu)
        log.info("트레이 아이콘 시작")
        icon.run()  # 메인 스레드 블로킹 — 종료 시까지 여기서 대기

    except ImportError:
        log.info("트레이 비활성 (pystray 없음) — asyncio 스레드 종료 대기")
        t.join()
    except KeyboardInterrupt:
        if _loop_holder and _stop_holder:
            _loop_holder[0].call_soon_threadsafe(_stop_holder[0].set)
        t.join()


if __name__ == "__main__":
    entry()
