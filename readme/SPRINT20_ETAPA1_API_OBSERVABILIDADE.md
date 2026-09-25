# Sprint 20 — Etapa 1: API local e observabilidade

## Objetivo

Criar a fundação HTTP do Atlas sem duplicar o núcleo nem expor comandos antes
da implementação de autenticação.

## Entrega

- aplicação FastAPI independente;
- contrato versionado em `/api/v1`;
- `GET /api/v1/health`;
- `GET /api/v1/version`;
- `GET /api/v1/status`;
- documentação OpenAPI em `/docs`;
- execução restrita a `127.0.0.1`;
- métricas de CPU e memória sem caminhos ou processos locais;
- testes HTTP determinísticos.

## Execução

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe api_main.py
```

A documentação estará disponível em `http://127.0.0.1:8765/docs`.

## Validação

```powershell
.\.venv\Scripts\python.exe -m pytest -q atlas/tests/test_api_observability.py
.\.venv\Scripts\python.exe -m ruff check atlas/api atlas/version.py api_main.py atlas/tests/test_api_observability.py atlas/core/config.py atlas/__init__.py
```

## Limite de segurança

Esta etapa é exclusivamente de leitura. Execução e cancelamento de comandos
serão adicionados somente depois da autenticação e do modelo de permissões.
