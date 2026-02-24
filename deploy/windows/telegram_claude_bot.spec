# -*- mode: python ; coding: utf-8 -*-
import os

# 프로젝트 루트 (spec 파일 위치 기준 두 단계 위)
_HERE = os.path.dirname(os.path.abspath(SPEC))
_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
_DIST = os.path.join(_ROOT, 'dist')

# src/assets 폴더가 존재할 때만 datas에 포함
_assets_src = os.path.join(_ROOT, 'src', 'assets')
_datas = []
if os.path.isdir(_assets_src):
    _datas.append((_assets_src, 'assets'))

# (참고) .env.example은 빌드 후 EXE 옆에 자동 복사됨 (spec 하단 참조)

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
        'src.shared.ai_session',
        'src.shared.chat_history',
        'src.shared.named_sessions',
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

# 빌드 후: 배포 파일들을 EXE 옆에 복사
import shutil
_dist_dir = os.path.join(_DIST, 'telegram_claude_bot')
_win_deploy = os.path.join(_ROOT, 'deploy', 'windows')

_copy_files = [
    (os.path.join(_ROOT, '.env.example'),               '.env.example'),
    (os.path.join(_win_deploy, 'install_service.bat'),  'install_service.bat'),
    (os.path.join(_win_deploy, 'remove_service.bat'),   'remove_service.bat'),
    (os.path.join(_win_deploy, 'install_service.ps1'),  'install_service.ps1'),
    (os.path.join(_win_deploy, 'remove_service.ps1'),   'remove_service.ps1'),
]

if os.path.isdir(_dist_dir):
    for src, dst_name in _copy_files:
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(_dist_dir, dst_name))
            print(f"[spec] 복사 완료: {dst_name} -> {_dist_dir}")
