from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.paths import RuntimePaths, resolve_runtime_paths


def test_source_mode_preserves_project_local_paths(tmp_path: Path) -> None:
    module = tmp_path / "atlas" / "core" / "paths.py"
    result = resolve_runtime_paths(
        frozen=False,
        module_file=module,
        environ={},
    )
    assert result.install_root == tmp_path
    assert result.user_root == tmp_path
    assert result.data_dir == tmp_path / "data"
    assert result.log_dir == tmp_path / "logs"
    assert result.config_file == tmp_path / ".env"
    assert result.frozen is False


def test_frozen_mode_uses_executable_directory_and_local_app_data(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "Programs" / "Atlas" / "Atlas.exe"
    local = tmp_path / "Local"
    result = resolve_runtime_paths(
        frozen=True,
        executable=executable,
        module_file=tmp_path / "ignored.py",
        environ={"LOCALAPPDATA": str(local)},
    )
    assert result.install_root == executable.parent.resolve()
    assert result.user_root == local.resolve() / "Atlas"
    assert result.data_dir == local.resolve() / "Atlas" / "data"
    assert result.config_file == local.resolve() / "Atlas" / ".env"


def test_explicit_user_data_directory_has_priority(tmp_path: Path) -> None:
    custom = tmp_path / "CustomData"
    result = resolve_runtime_paths(
        frozen=True,
        executable=tmp_path / "Atlas.exe",
        environ={
            "LOCALAPPDATA": str(tmp_path / "Local"),
            "ATLAS_USER_DATA_DIR": str(custom),
        },
    )
    assert result.user_root == custom.resolve()


def test_blank_explicit_directory_is_ignored(tmp_path: Path) -> None:
    local = tmp_path / "Local"
    result = resolve_runtime_paths(
        frozen=True,
        executable=tmp_path / "Atlas.exe",
        environ={"LOCALAPPDATA": str(local), "ATLAS_USER_DATA_DIR": "  "},
    )
    assert result.user_root == local.resolve() / "Atlas"


def test_path_resolution_does_not_create_directories(tmp_path: Path) -> None:
    target = tmp_path / "not-created"
    result = resolve_runtime_paths(
        frozen=True,
        executable=tmp_path / "Atlas.exe",
        environ={"ATLAS_USER_DATA_DIR": str(target)},
    )
    assert result.user_root == target.resolve()
    assert target.exists() is False


def test_runtime_paths_is_immutable(tmp_path: Path) -> None:
    result = resolve_runtime_paths(
        frozen=False,
        module_file=tmp_path / "atlas" / "core" / "paths.py",
        environ={},
    )
    with pytest.raises(Exception):
        result.user_root = tmp_path / "other"  # type: ignore[misc]


def test_runtime_paths_contract_accepts_paths(tmp_path: Path) -> None:
    value = RuntimePaths(
        install_root=tmp_path,
        user_root=tmp_path,
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        config_file=tmp_path / ".env",
        frozen=False,
    )
    assert value.data_dir.name == "data"


def test_source_mode_ignores_local_app_data(tmp_path: Path) -> None:
    result = resolve_runtime_paths(
        frozen=False,
        module_file=tmp_path / "atlas" / "core" / "paths.py",
        environ={"LOCALAPPDATA": str(tmp_path / "elsewhere")},
    )
    assert result.user_root == tmp_path

