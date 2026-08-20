"""Teste manual da pesquisa rastreável da Sprint 22."""

from __future__ import annotations

import argparse

from atlas.internet import (
    WebSearchRequest,
    build_default_web_search_service,
    build_local_search_principal,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pesquisa em fontes configuradas pelo Atlas.",
    )
    parser.add_argument("query", help="Assunto que será pesquisado.")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Total de resultados entre 1 e 20.",
    )
    arguments = parser.parse_args()
    service = build_default_web_search_service()
    response = service.search(
        WebSearchRequest(
            query=arguments.query,
            max_results=arguments.limit,
        ),
        build_local_search_principal(),
    )
    print(response.format_message())
    return 0 if response.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
