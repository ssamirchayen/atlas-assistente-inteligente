from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_spec_packages_sprint26_frontend_and_single_instance() -> None:
    source = (ROOT / "packaging" / "atlas.spec").read_text(encoding="utf-8")
    assert 'project_root / "gui_main.py"' in source
    assert '"atlas.gui.orb"' in source
    assert '"atlas.gui.theme"' in source
    assert '"atlas.gui.single_instance"' in source
    assert "console=False" in source
    ast.parse(source)


def test_installer_identifies_atlas_core_1_and_nexyra() -> None:
    source = (ROOT / "packaging" / "windows" / "atlas.iss").read_text(
        encoding="utf-8"
    )
    assert '#define MyAppVersion "1.0.0"' in source
    assert '#define MyAppPublisher "NEXYRA"' in source
    assert "AppId={{9C4A7189-12CC-4F89-83D8-A57651E6ECA4}" in source


def test_build_detects_user_local_inno_setup() -> None:
    source = (ROOT / "tools" / "build_windows_installer.ps1").read_text(
        encoding="utf-8"
    )
    assert '$env:LOCALAPPDATA\\Programs\\Inno Setup 6\\ISCC.exe' in source


def test_build_runs_frontend_preflight_before_pyinstaller() -> None:
    source = (ROOT / "tools" / "build_windows_installer.ps1").read_text(
        encoding="utf-8"
    )
    assert source.index("-m tools.validate_sprint26_frontend") < source.index(
        "-m PyInstaller"
    )


def test_build_validates_release_before_installer() -> None:
    source = (ROOT / "tools" / "build_windows_installer.ps1").read_text(
        encoding="utf-8"
    )
    assert source.index("-m tools.validate_release") < source.index(
        '& $IsccPath'
    )


def test_build_keeps_tests_and_ruff_enabled_by_default() -> None:
    source = (ROOT / "tools" / "build_windows_installer.ps1").read_text(
        encoding="utf-8"
    )
    assert "-m pytest -q" in source
    assert "-m ruff check ." in source
    assert "[switch]$SkipTests" in source


def test_build_emits_sha256_for_exe_and_installer() -> None:
    source = (ROOT / "tools" / "build_windows_installer.ps1").read_text(
        encoding="utf-8"
    )
    assert "Get-FileHash -Algorithm SHA256" in source
    assert "SHA256 EXE" in source
    assert "SHA256 SETUP" in source
