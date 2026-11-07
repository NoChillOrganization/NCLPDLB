# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for NCLPDLB standalone .exe
# Build from src/bot/ directory:  pyinstaller NCLPDLB.spec
# Output: src/bot/dist/NCLPDLB.exe  (~100-200 MB)

import os
import warnings
from pathlib import Path

# Suppress pydantic V1 incompatibility warning on Python 3.14
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Resolve project root (2 levels up from src/bot/ → pokemon-draft-bot/)
project_root = str(Path(SPECPATH).parent.parent)

# credentials.json and .env are deliberately NOT bundled (secrets); place them
# next to the exe at runtime.
datas = [
    (str(Path(project_root) / 'data' / 'pokemon.json'), 'data'),
]

a = Analysis(
    ['main.py'],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'discord',
        'discord.ext.commands',
        'discord.ui',
        'gspread',
        'google.auth',
        'google.oauth2.service_account',
        'aiosqlite',
        'pydantic_settings',
        'src.bot.cogs.draft',
        'src.bot.cogs.team',
        'src.bot.cogs.league',
        'src.bot.cogs.admin',
        'src.bot.cogs.stats',
        'src.bot.cogs.sheet',
        'src.bot.cogs.misc',
        'src.bot.cogs.ml',
        'src.bot.views.draft_view',
        'src.bot.views.team_view',
        'src.services.draft_service',
        'src.services.team_service',
        'src.services.elo_service',
        'src.services.analytics_service',
        'src.services.battle_sim',
        'src.services.video_service',
        'src.services.notification_service',
        'src.data.db',
        'src.data.learning_sheets',
        'src.data.models',
        'src.data.pokeapi',
        'src.data.sheets',
        'src.data.showdown',
        'src.data.smogon',
    ],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'fastapi',
        'uvicorn',
        'boto3',
        'botocore',
        'azure',
        'ffmpeg',
        'locust',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NCLPDLB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
