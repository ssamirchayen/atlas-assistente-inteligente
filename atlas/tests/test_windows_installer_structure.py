from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_pyinstaller_spec_uses_gui_entrypoint_and_onedir() -> None:
    source = (ROOT / "packaging" / "atlas.spec").read_text(encoding="utf-8")
    assert 'project_root / "gui_main.py"' in source
    assert "COLLECT(" in source
    assert 'name="Atlas"' in source
    assert "console=False" in source
    assert 'contents_directory="."' in source


def test_pyinstaller_spec_includes_only_example_configuration() -> None:
    source = (ROOT / "packaging" / "atlas.spec").read_text(encoding="utf-8")
    assert 'project_root / ".env.example"' in source
    assert 'project_root / ".env"' not in source
    assert 'project_root / "data"' not in source
    assert 'project_root / "logs"' not in source


def test_spec_is_valid_python_syntax() -> None:
    source = (ROOT / "packaging" / "atlas.spec").read_text(encoding="utf-8")
    ast.parse(source)


def test_manifest_forbids_private_runtime_files() -> None:
    payload = json.loads(
        (ROOT / "packaging" / "release_manifest.json").read_text(encoding="utf-8")
    )
    assert ".env" in payload["forbidden_names"]
    assert ".db" in payload["forbidden_suffixes"]
    assert "data" in payload["forbidden_directories"]
    assert "logs" in payload["forbidden_directories"]


def test_build_runs_validation_before_inno_setup() -> None:
    source = (ROOT / "tools" / "build_windows_installer.ps1").read_text(
        encoding="utf-8"
    )
    assert source.index("-m tools.validate_release") < source.index(
        '& $IsccPath'
    )


def test_build_runs_tests_and_ruff_by_default() -> None:
    source = (ROOT / "tools" / "build_windows_installer.ps1").read_text(
        encoding="utf-8"
    )
    assert "-m pytest -q" in source
    assert "-m ruff check ." in source
    assert "[switch]$SkipTests" in source


def test_build_does_not_download_models_or_remote_scripts() -> None:
    source = (ROOT / "tools" / "build_windows_installer.ps1").read_text(
        encoding="utf-8"
    ).casefold()
    assert "ollama pull" not in source
    assert "invoke-webrequest" not in source
    assert "curl" not in source


def test_installer_is_per_user_and_does_not_require_admin() -> None:
    source = (ROOT / "packaging" / "windows" / "atlas.iss").read_text(
        encoding="utf-8"
    )
    assert "DefaultDirName={localappdata}\\Programs\\Atlas" in source
    assert "PrivilegesRequired=lowest" in source
    assert "runascurrentuser" not in source.casefold()


def test_uninstall_preserves_user_data() -> None:
    source = (ROOT / "packaging" / "windows" / "atlas.iss").read_text(
        encoding="utf-8"
    )
    assert 'Name: "{localappdata}\\Atlas"; Flags: uninsneveruninstall' in source
    assert "[UninstallDelete]" not in source


def test_desktop_shortcut_is_optional() -> None:
    source = (ROOT / "packaging" / "windows" / "atlas.iss").read_text(
        encoding="utf-8"
    )
    assert 'Name: "desktopicon"' in source
    assert "Flags: unchecked" in source


def test_frozen_runtime_uses_local_app_data() -> None:
    source = (ROOT / "atlas" / "core" / "paths.py").read_text(encoding="utf-8")
    assert 'environment.get("LOCALAPPDATA"' in source
    assert 'user_root / "data"' in source
    assert 'user_root / "logs"' in source


def test_frozen_runtime_defaults_to_system_edge() -> None:
    source = (ROOT / "atlas" / "core" / "config.py").read_text(encoding="utf-8")
    assert '"msedge" if RUNTIME_PATHS.frozen else ""' in source
    browser = (ROOT / "atlas" / "automation" / "browser.py").read_text(
        encoding="utf-8"
    )
    assert 'launch_options["channel"] = BROWSER_CHANNEL' in browser


def test_installer_does_not_delete_existing_configuration() -> None:
    source = (ROOT / "packaging" / "windows" / "atlas.iss").read_text(
        encoding="utf-8"
    ).casefold()
    assert "deleteafterinstall" not in source
    assert "[uninstalldelete]" not in source
    assert "onlyifdoesntexist uninsneveruninstall" in source
