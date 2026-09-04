from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.packaging.release import (
    ReleasePolicy,
    ReleaseValidator,
    load_release_policy,
)


def policy(*, max_size: int = 2) -> ReleasePolicy:
    return ReleasePolicy(
        schema_version=1,
        product_name="Atlas Core",
        required_files=("Atlas.exe", ".env.example", "assets/atlas.svg"),
        forbidden_names=frozenset({".env", "memory.db"}),
        forbidden_suffixes=frozenset({".db", ".log", ".pem"}),
        forbidden_directories=frozenset({"data", "logs", "__pycache__"}),
        max_file_size_mb=max_size,
    )


def valid_release(tmp_path: Path) -> Path:
    root = tmp_path / "Atlas"
    (root / "assets").mkdir(parents=True)
    (root / "Atlas.exe").write_bytes(b"MZ-demo")
    (root / ".env.example").write_text("ATLAS_MODEL=atlas", encoding="utf-8")
    (root / "assets" / "atlas.svg").write_text("<svg/>", encoding="utf-8")
    return root


def test_valid_release_passes(tmp_path: Path) -> None:
    report = ReleaseValidator(policy()).validate(valid_release(tmp_path))
    assert report.valid is True
    assert report.file_count == 3
    assert report.total_size_bytes > 0
    assert report.issues == ()


def test_missing_root_fails_closed(tmp_path: Path) -> None:
    report = ReleaseValidator(policy()).validate(tmp_path / "missing")
    assert report.valid is False
    assert report.issues[0].code == "release_root_missing"


@pytest.mark.parametrize("required", ["Atlas.exe", ".env.example", "assets/atlas.svg"])
def test_missing_required_file_is_reported(tmp_path: Path, required: str) -> None:
    root = valid_release(tmp_path)
    (root / required).unlink()
    report = ReleaseValidator(policy()).validate(root)
    assert any(
        issue.code == "required_file_missing" and issue.relative_path == required
        for issue in report.issues
    )


@pytest.mark.parametrize(
    ("relative", "code"),
    [
        (".env", "file_name_forbidden"),
        ("memory.db", "file_name_forbidden"),
        ("private.pem", "file_suffix_forbidden"),
        ("atlas.log", "file_suffix_forbidden"),
    ],
)
def test_forbidden_files_are_reported(
    tmp_path: Path,
    relative: str,
    code: str,
) -> None:
    root = valid_release(tmp_path)
    (root / relative).write_text("secret", encoding="utf-8")
    report = ReleaseValidator(policy()).validate(root)
    assert any(issue.code == code and issue.relative_path == relative for issue in report.issues)


def test_exact_public_certificate_bundle_can_be_allowed(tmp_path: Path) -> None:
    root = valid_release(tmp_path)
    bundle = root / "certifi" / "cacert.pem"
    bundle.parent.mkdir()
    bundle.write_text("public certificate authorities", encoding="utf-8")
    base = policy()
    configured = ReleasePolicy(
        schema_version=base.schema_version,
        product_name=base.product_name,
        required_files=base.required_files,
        forbidden_names=base.forbidden_names,
        forbidden_suffixes=base.forbidden_suffixes,
        forbidden_directories=base.forbidden_directories,
        max_file_size_mb=base.max_file_size_mb,
        allowed_suffix_paths=frozenset({"certifi/cacert.pem"}),
    )

    report = ReleaseValidator(configured).validate(root)

    assert report.valid is True


def test_allowlist_does_not_release_other_pem_files(tmp_path: Path) -> None:
    root = valid_release(tmp_path)
    private = root / "private.pem"
    private.write_text("secret", encoding="utf-8")
    base = policy()
    configured = ReleasePolicy(
        schema_version=base.schema_version,
        product_name=base.product_name,
        required_files=base.required_files,
        forbidden_names=base.forbidden_names,
        forbidden_suffixes=base.forbidden_suffixes,
        forbidden_directories=base.forbidden_directories,
        max_file_size_mb=base.max_file_size_mb,
        allowed_suffix_paths=frozenset({"certifi/cacert.pem"}),
    )

    report = ReleaseValidator(configured).validate(root)

    assert any(
        issue.code == "file_suffix_forbidden"
        and issue.relative_path == "private.pem"
        for issue in report.issues
    )


@pytest.mark.parametrize("name", ["data", "logs", "__pycache__"])
def test_forbidden_directory_is_reported(tmp_path: Path, name: str) -> None:
    root = valid_release(tmp_path)
    (root / name).mkdir()
    report = ReleaseValidator(policy()).validate(root)
    assert any(issue.code == "directory_forbidden" for issue in report.issues)


def test_file_too_large_is_reported(tmp_path: Path) -> None:
    root = valid_release(tmp_path)
    large = root / "large.bin"
    large.write_bytes(b"x" * (1024 * 1024 + 1))
    report = ReleaseValidator(policy(max_size=1)).validate(root)
    assert any(issue.code == "file_too_large" for issue in report.issues)


def test_symlink_is_rejected(tmp_path: Path) -> None:
    root = valid_release(tmp_path)
    try:
        (root / "link.exe").symlink_to(root / "Atlas.exe")
    except OSError:
        pytest.skip("O ambiente não permite symlinks.")
    report = ReleaseValidator(policy()).validate(root)
    assert any(issue.code == "symlink_forbidden" for issue in report.issues)


def test_public_summary_uses_only_codes_and_relative_paths(tmp_path: Path) -> None:
    root = valid_release(tmp_path)
    (root / ".env").write_text("ATLAS_API_KEY=segredo", encoding="utf-8")
    summary = ReleaseValidator(policy()).validate(root).public_summary()
    assert "segredo" not in repr(summary)
    assert summary["valid"] is False


def write_manifest(tmp_path: Path, payload) -> Path:
    target = tmp_path / "manifest.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def manifest_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "product_name": "Atlas Core",
        "required_files": ["Atlas.exe"],
        "forbidden_names": [".env"],
        "forbidden_suffixes": [".db"],
        "forbidden_directories": ["data"],
        "max_file_size_mb": 100,
    }


def test_manifest_loads_and_normalizes_case(tmp_path: Path) -> None:
    payload = manifest_payload()
    payload["forbidden_names"] = ["MEMORY.DB"]
    loaded = load_release_policy(write_manifest(tmp_path, payload))
    assert loaded.product_name == "Atlas Core"
    assert "memory.db" in loaded.forbidden_names


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {**manifest_payload(), "schema_version": 2},
        {**manifest_payload(), "product_name": ""},
        {**manifest_payload(), "required_files": []},
        {**manifest_payload(), "required_files": ["../Atlas.exe"]},
        {**manifest_payload(), "required_files": ["C:/Atlas.exe"]},
        {**manifest_payload(), "required_files": ["Atlas exe"]},
        {**manifest_payload(), "max_file_size_mb": 0},
    ],
)
def test_invalid_manifest_is_rejected(tmp_path: Path, payload) -> None:
    with pytest.raises(ValueError):
        load_release_policy(write_manifest(tmp_path, payload))


def test_malformed_json_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    target.write_text("{invalid", encoding="utf-8")
    with pytest.raises(ValueError, match="manifesto"):
        load_release_policy(target)


def test_issue_order_is_deterministic(tmp_path: Path) -> None:
    root = valid_release(tmp_path)
    (root / "z.log").write_text("x", encoding="utf-8")
    (root / "a.log").write_text("x", encoding="utf-8")
    issues = ReleaseValidator(policy()).validate(root).issues
    assert issues == tuple(sorted(issues, key=lambda item: (item.code, item.relative_path or "")))
