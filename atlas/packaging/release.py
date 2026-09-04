"""Política fail-closed para validar a saída do instalador."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


_SAFE_RELATIVE = re.compile(r"^[A-Za-z0-9._/+-]+$")


@dataclass(frozen=True, slots=True)
class ReleasePolicy:
    schema_version: int
    product_name: str
    required_files: tuple[str, ...]
    forbidden_names: frozenset[str]
    forbidden_suffixes: frozenset[str]
    forbidden_directories: frozenset[str]
    max_file_size_mb: int
    allowed_suffix_paths: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Versão de manifesto não suportada.")
        if not self.product_name.strip():
            raise ValueError("product_name é obrigatório.")
        if not self.required_files:
            raise ValueError("required_files não pode ser vazio.")
        for path in self.required_files:
            _validate_relative_path(path)
        for path in self.allowed_suffix_paths:
            _validate_relative_path(path)
        if self.max_file_size_mb < 1:
            raise ValueError("max_file_size_mb deve ser positivo.")


@dataclass(frozen=True, slots=True)
class ReleaseIssue:
    code: str
    relative_path: str | None = None


@dataclass(frozen=True, slots=True)
class ReleaseReport:
    valid: bool
    file_count: int
    total_size_bytes: int
    issues: tuple[ReleaseIssue, ...]

    def public_summary(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "issues": [
                {"code": issue.code, "relative_path": issue.relative_path}
                for issue in self.issues
            ],
        }


def _validate_relative_path(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_RELATIVE.fullmatch(value):
        raise ValueError("Caminho relativo inválido no manifesto.")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Caminho relativo inseguro no manifesto.")
    return path.as_posix()


def load_release_policy(path: str | Path) -> ReleasePolicy:
    manifest_path = Path(path)
    try:
        payload: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Não foi possível ler o manifesto de release.") from exc
    if not isinstance(payload, dict):
        raise ValueError("O manifesto deve ser um objeto JSON.")
    try:
        return ReleasePolicy(
            schema_version=payload["schema_version"],
            product_name=payload["product_name"],
            required_files=tuple(payload["required_files"]),
            forbidden_names=frozenset(
                str(value).casefold() for value in payload["forbidden_names"]
            ),
            forbidden_suffixes=frozenset(
                str(value).casefold() for value in payload["forbidden_suffixes"]
            ),
            forbidden_directories=frozenset(
                str(value).casefold() for value in payload["forbidden_directories"]
            ),
            max_file_size_mb=payload["max_file_size_mb"],
            allowed_suffix_paths=frozenset(
                _validate_relative_path(str(value)).casefold()
                for value in payload.get("allowed_suffix_paths", [])
            ),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("Manifesto de release incompleto.") from exc


class ReleaseValidator:
    def __init__(self, policy: ReleasePolicy) -> None:
        self.policy = policy

    def validate(self, root: str | Path) -> ReleaseReport:
        release_root = Path(root).resolve()
        if not release_root.is_dir():
            return ReleaseReport(
                valid=False,
                file_count=0,
                total_size_bytes=0,
                issues=(ReleaseIssue("release_root_missing"),),
            )

        issues: list[ReleaseIssue] = []
        files: list[Path] = []
        total_size = 0
        for path in sorted(release_root.rglob("*")):
            relative = path.relative_to(release_root).as_posix()
            if path.is_symlink():
                issues.append(ReleaseIssue("symlink_forbidden", relative))
                continue
            if path.is_dir():
                if path.name.casefold() in self.policy.forbidden_directories:
                    issues.append(ReleaseIssue("directory_forbidden", relative))
                continue
            if not path.is_file():
                issues.append(ReleaseIssue("unsupported_entry", relative))
                continue
            files.append(path)
            try:
                size = path.stat().st_size
            except OSError:
                issues.append(ReleaseIssue("file_unreadable", relative))
                continue
            total_size += size
            name = path.name.casefold()
            suffix = path.suffix.casefold()
            if name in self.policy.forbidden_names:
                issues.append(ReleaseIssue("file_name_forbidden", relative))
            if (
                suffix in self.policy.forbidden_suffixes
                and relative.casefold() not in self.policy.allowed_suffix_paths
            ):
                issues.append(ReleaseIssue("file_suffix_forbidden", relative))
            if size > self.policy.max_file_size_mb * 1024 * 1024:
                issues.append(ReleaseIssue("file_too_large", relative))

        for required in self.policy.required_files:
            target = release_root.joinpath(*PurePosixPath(required).parts)
            if not target.is_file() or target.is_symlink():
                issues.append(ReleaseIssue("required_file_missing", required))

        ordered = tuple(
            sorted(issues, key=lambda item: (item.code, item.relative_path or ""))
        )
        return ReleaseReport(
            valid=not ordered,
            file_count=len(files),
            total_size_bytes=total_size,
            issues=ordered,
        )


__all__ = [
    "ReleaseIssue",
    "ReleasePolicy",
    "ReleaseReport",
    "ReleaseValidator",
    "load_release_policy",
]
