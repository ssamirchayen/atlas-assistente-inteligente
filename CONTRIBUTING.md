# Desenvolvimento e contribuições

Este repositório é publicado principalmente para avaliação técnica e portfólio.
O recebimento de uma sugestão ou pull request não concede direitos sobre o
produto nem garante que a alteração será incorporada.

## Preparação

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Antes de enviar uma alteração

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q atlas main.py gui_main.py
```

Não inclua dados de `data/`, `atlas_data/`, `logs/`, `.env` ou qualquer
informação pessoal. Novos comportamentos devem incluir testes automatizados e
respeitar as responsabilidades descritas em `docs/ARCHITECTURE.md`.
