# -*- mode: python ; coding: utf-8 -*-
import os

# 프로젝트 루트 (spec 파일 위치 기준 두 단계 위)
_HERE = os.path.dirname(os.path.abspath(SPEC))
_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))

# src/assets 폴더가 존재할 때만 datas에 포함
_assets_src = os.path.join(_ROOT, 'src', 'assets')
_datas = []
if os.path.isdir(_assets_src):
    _datas.append((_assets_src, 'assets'))

a = Analysis(
    [os.path.join(_ROOT, 'src', 'main.py')],
    pathex=[_ROOT],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'pydantic',
        'pydantic_settings',
        'aiosqlite',
        'structlog',
        'telegram',
        'telegram.ext',
        'telegram.ext._application',
        'telegram.ext._updater',
        'telegram.ext._jobqueue',
        'src.shared.config',
        'src.shared.models',
        'src.shared.database',
        'src.shared.events',
        'src.orchestrator.manager',
        'src.orchestrator.process',
        'src.orchestrator.queue',
        'src.telegram.bot',
        'src.telegram.handlers.commands',
        'src.telegram.handlers.callbacks',
        'src.telegram.keyboards',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='telegram_claude_bot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='telegram_claude_bot',
)
