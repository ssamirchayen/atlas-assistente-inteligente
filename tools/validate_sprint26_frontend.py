"""Pré-validação da build desktop da Sprint 26."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "gui_main.py",
    "atlas/gui/window.py",
    "atlas/gui/theme.py",
    "atlas/gui/orb.py",
    "atlas/gui/single_instance.py",
    "atlas/gui/admin_console.py",
    "packaging/atlas.spec",
    "packaging/windows/atlas.iss",
    "packaging/release_manifest.json",
)


def _contains(path: str, *tokens: str) -> bool:
    text = (ROOT / path).read_text(encoding="utf-8")
    return all(token in text for token in tokens)


def validate() -> dict[str, object]:
    issues: list[str] = []

    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            issues.append(f"missing:{relative}")

    if not issues:
        checks = {
            "single_instance": _contains(
                "gui_main.py",
                "multiprocessing.freeze_support()",
                "SingleInstanceGuard",
            ),
            "premium_theme": _contains(
                "atlas/gui/theme.py",
                "SPRINT 26",
                "PREMIUM UI",
                "LIVE INTERFACE",
            ),
            "live_orb": _contains(
                "atlas/gui/window.py",
                "AtlasOrb",
                "self.atlas_orb.set_state",
            ),
            "official_backend": _contains(
                "atlas/gui/window.py",
                "AtlasGuiService",
                "SerialCommandRunner",
                "self.service.execute",
            ),
            "pyinstaller_frontend": _contains(
                "packaging/atlas.spec",
                "atlas.gui.orb",
                "atlas.gui.theme",
                "atlas.gui.single_instance",
                "console=False",
            ),
            "installer_v1": _contains(
                "packaging/windows/atlas.iss",
                '#define MyAppVersion "1.0.0"',
                '#define MyAppPublisher "NEXYRA"',
            ),
        }
        for name, passed in checks.items():
            if not passed:
                issues.append(f"check_failed:{name}")

    report: dict[str, object] = {
        "valid": not issues,
        "release": "Atlas Core 1.0.0",
        "frontend": "Sprint 26 Premium UI / Live Interface",
        "issues": issues,
    }
    return report


def main() -> int:
    report = validate()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
