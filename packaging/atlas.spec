# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

project_root = Path(SPECPATH).resolve().parent

frontend_hiddenimports = [
    "atlas.gui.admin_console",
    "atlas.gui.orb",
    "atlas.gui.single_instance",
    "atlas.gui.theme",
]

voice_hiddenimports = [
    "edge_tts",
    "edge_tts.communicate",
    "edge_tts.voices",
    "aiohttp",
    "certifi",
    "atlas.voice.tts",
    "atlas.voice.tts_cache",
    "atlas.voice.playback",
    "atlas.voice.command_normalizer",
    "atlas.voice.response",
    "atlas.voice.profile",
    "atlas.voice.latency",
    "atlas.voice.interruption",
    "atlas.voice.continuous",
    "atlas.voice.session",
    "atlas.voice.pipeline",
]

edge_datas, edge_binaries, edge_hidden = collect_all("edge_tts")
certifi_datas = collect_data_files("certifi")
try:
    edge_metadata = copy_metadata("edge-tts")
except Exception:
    edge_metadata = []

asset_dir = project_root / "atlas" / "gui" / "assets"
datas = [(str(project_root / ".env.example"), ".")]
if asset_dir.exists():
    datas.append((str(asset_dir), "atlas/gui/assets"))
datas.extend(edge_datas)
datas.extend(certifi_datas)
datas.extend(edge_metadata)

a = Analysis(
    [str(project_root / "gui_main.py")],
    pathex=[str(project_root)],
    binaries=[*edge_binaries],
    datas=datas,
    hiddenimports=[
        "speech_recognition",
        "pywinauto",
        *frontend_hiddenimports,
        *voice_hiddenimports,
        *edge_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "ruff", "tkinter"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Atlas",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Atlas",
)
