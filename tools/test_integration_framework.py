from __future__ import annotations

import importlib
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
    integration_manager = integrations.IntegrationManager
    register_default_connectors = (
        integrations.register_default_connectors
    )

    register_default_connectors()
    manager = integration_manager()

    print("Atlas Integration Framework")
    print(
        "Connectors:",
        ", ".join(manager.available_connectors()),
    )

    result = manager.execute(
        "business_lab",
        "health",
    )

    print(f"Business Lab OK: {result.ok}")
    print(
        "Driver:",
        result.driver.value if result.driver else None,
    )
    print("Dados:", result.data)
    if result.error:
        print("Erro:", result.error)

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
