"""Ponto de entrada da API local do Atlas."""

from __future__ import annotations

import uvicorn

from atlas.api.auth import ApiKeyAuthenticator
from atlas.core.config import API_HOST, API_PORT


def main() -> None:
    """Inicia a API somente na interface local por padrão."""

    try:
        authenticator = ApiKeyAuthenticator.from_environment()
    except ValueError as error:
        raise SystemExit(str(error)) from error

    if not authenticator.configured:
        raise SystemExit(
            "Configure ATLAS_API_KEY no arquivo .env antes de iniciar a API."
        )

    uvicorn.run(
        "atlas.api.app:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
