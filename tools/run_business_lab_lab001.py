from __future__ import annotations

import importlib
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

    integrations = importlib.import_module(
        "atlas.integrations"
    )

    email = os.getenv("ATLAS_BUSINESS_LAB_EMAIL")
    password = os.getenv(
        "ATLAS_BUSINESS_LAB_PASSWORD"
    )

    if not email or not password:
        print(
            "Configure ATLAS_BUSINESS_LAB_EMAIL e "
            "ATLAS_BUSINESS_LAB_PASSWORD antes do teste."
        )
        return 2

    connector_class = (
        integrations.BusinessLabConnector
    )
    registry_class = integrations.ConnectorRegistry
    manager_class = integrations.IntegrationManager

    registry = registry_class()
    registry.register(
        connector_class(
            email=email,
            password=password,
        )
    )
    manager = manager_class(registry)

    result = manager.execute(
        "business_lab",
        "get_lead",
        code="SIM-00001",
    )

    print("LAB-001 / execução por API")
    print("Connector: business_lab")
    print(
        "Driver:",
        result.driver.value if result.driver else None,
    )
    print("Sucesso:", result.ok)

    if not result.ok:
        print("Erro:", result.error)
        return 1

    lead = result.data or {}
    print("Código:", lead.get("synthetic_code"))
    print("Nome:", lead.get("name"))
    print("Curso:", lead.get("course_name"))
    print("Status:", lead.get("status"))
    print("Prioridade:", lead.get("priority"))

    if lead.get("synthetic_code") != "SIM-00001":
        print(
            "Falha: a API retornou um lead diferente."
        )
        return 1

    print(
        "\nConsulta concluída pelo Atlas Integration Framework."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
