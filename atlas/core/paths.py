"""Resolução de caminhos para código-fonte e distribuição congelada."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Mapping


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    install_root: Path
    user_root: Path
    data_dir: Path
    log_dir: Path
    config_file: Path
    frozen: bool


def resolve_runtime_paths(
    *,
    frozen: bool | None = None,
    executable: str | Path | None = None,
    module_file: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> RuntimePaths:
    environment = os.environ if environ is None else environ
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    source_file = Path(module_file or __file__).resolve()

    if is_frozen:
        install_root = Path(executable or sys.executable).resolve().parent
        explicit_root = environment.get("ATLAS_USER_DATA_DIR", "").strip()
        if explicit_root:
            user_root = Path(explicit_root).expanduser().resolve()
        else:
            local_app_data = environment.get("LOCALAPPDATA", "").strip()
            if local_app_data:
                user_root = Path(local_app_data).expanduser().resolve() / "Atlas"
            else:
                user_root = Path.home().resolve() / "AppData" / "Local" / "Atlas"
    else:
        install_root = source_file.parents[2]
        user_root = install_root

    return RuntimePaths(
        install_root=install_root,
        user_root=user_root,
        data_dir=user_root / "data",
        log_dir=user_root / "logs",
        config_file=user_root / ".env",
        frozen=is_frozen,
    )


__all__ = ["RuntimePaths", "resolve_runtime_paths"]

