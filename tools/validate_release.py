"""Valida a pasta produzida pelo PyInstaller antes do Inno Setup."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlas.packaging.release import ReleaseValidator, load_release_policy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validador de release do Atlas")
    parser.add_argument("release_dir", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("packaging/release_manifest.json"),
    )
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        policy = load_release_policy(arguments.manifest)
        report = ReleaseValidator(policy).validate(arguments.release_dir)
    except ValueError as error:
        print(json.dumps({"valid": False, "error_type": type(error).__name__}))
        return 2
    print(json.dumps(report.public_summary(), ensure_ascii=False, indent=2))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

