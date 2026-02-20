# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec - Claude Control Tower (onedir 배포)"""
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    [str(root / "src" / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / ".env.example"), "."),
        (str(root / "scripts"), "scripts"),
    ],
    hiddenimports=[
        "telegram", "telegram.ext",
        "httpx", "httpx._transports", "httpx._transports.default",
        "httpcore", "httpcore._async", "httpcore._sync",
        "h11", "anyio", "anyio._backends", "anyio._backends._asyncio",
        "sniffio", "certifi",
        "pydantic", "pydantic_settings", "annotated_types",
        "aiosqlite", "structlog", "psutil", "mss", "mss.tools",
        "pystray", "pystray._base", "pystray._win32",
        "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont",
        "src", "src.main",
        "src.shared", "src.shared.config", "src.shared.models",
        "src.shared.database", "src.shared.events",
        "src.shared.chat_history", "src.shared.claude_session",
        "src.orchestrator", "src.orchestrator.manager",
        "src.orchestrator.process", "src.orchestrator.queue",
        "src.telegram", "src.telegram.bot", "src.telegram.keyboards",
        "src.telegram.handlers", "src.telegram.handlers.commands",
        "src.telegram.handlers.callbacks",
    ],
    excludes=["tkinter", "matplotlib", "numpy", "scipy", "PIL", "pytest", "mypy", "ruff"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="controltower",
    debug=False, strip=False, upx=True,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="controltower",
)
