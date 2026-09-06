from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path


def _ensure_project_root() -> None:
    project_root = Path(__file__).resolve().parents[1]
    root = str(project_root)
    if root not in sys.path:
        sys.path.insert(0, root)


def main() -> int:
    _ensure_project_root()

    integrations = importlib.import_module("atlas.integrations")
    runner_module = importlib.import_module(
        "atlas.integrations.business_lab.lab_runner"
    )

    email = os.getenv("ATLAS_BUSINESS_LAB_EMAIL")
    password = os.getenv("ATLAS_BUSINESS_LAB_PASSWORD")

    if not email or not password:
        print(
            "Configure ATLAS_BUSINESS_LAB_EMAIL e "
            "ATLAS_BUSINESS_LAB_PASSWORD antes do teste."
        )
        return 2

    connector = integrations.BusinessLabConnector(
        email=email,
        password=password,
    )
    runner = runner_module.BusinessLabScenarioRunner(connector)
    summary = runner.run_all()

    print("Atlas Business Lab / LAB-001 a LAB-010")
    print("Modo: API pelo Integration Framework")
    print("Gabaritos oficiais expostos: NÃO")
    print("-" * 72)

    for record in summary.records:
        status = "OK" if record.ok else "FALHOU"
        driver = record.driver or "nenhum"
        print(f"{record.scenario_id} | {status} | driver={driver} | {record.title}")
        print(f"  {record.message}")
        if record.data:
            compact = json.dumps(record.data, ensure_ascii=False)
            print(f"  dados: {compact[:420]}")

    print("-" * 72)
    print(
        f"Resumo: {summary.passed}/{summary.total} cenários "
        f"operacionais passaram."
    )

    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
