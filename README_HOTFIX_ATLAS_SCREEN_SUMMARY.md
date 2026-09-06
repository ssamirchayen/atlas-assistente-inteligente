# Hotfix — Resumo de tela sem lead aberto

Corrige o caso em que o usuário está na lista de leads ou no dashboard e manda:

```text
Atlas, resuma essa tela
```

Antes o Atlas tentava resumir um lead específico e retornava erro por falta de `lead_code`.
Agora, quando não há lead aberto, o Atlas gera um resumo da tela atual usando dashboard + amostra de leads.

## Arquivos alterados

```text
atlas/copilot/business_lab.py
tests/test_atlas_copilot_screen_summary_hotfix.py
```

## Teste

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q tests\test_atlas_copilot_screen_summary_hotfix.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```
