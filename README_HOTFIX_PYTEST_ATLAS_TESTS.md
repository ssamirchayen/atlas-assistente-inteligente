# Hotfix — Pytest coletar tests e atlas/tests

Este hotfix ajusta o `pytest.ini` para que o comando padrão:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

colete tanto os testes novos da Sprint 28 em `tests/` quanto a suíte histórica do Atlas em `atlas/tests/`.

## O que mudou

```ini
[pytest]
testpaths =
    tests
    atlas/tests
```

A pasta `tools/` continua ignorada para evitar o conflito de import do arquivo `tools/test_integration_framework.py`.

## Como validar

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest --collect-only -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Se algum teste antigo em `atlas/tests/` falhar, isso significa que ele voltou a ser executado e precisará ser corrigido ou atualizado conforme a arquitetura atual.
