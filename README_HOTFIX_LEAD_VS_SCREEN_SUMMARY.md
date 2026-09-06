# Hotfix — Resumo de tela sem quebrar resumo de lead

Este hotfix corrige a regressão em que o comando **"Resuma esse lead"** sem `lead_code` passou a cair em resumo de tela.

## Correção

- `Atlas, resuma essa tela` continua funcionando em `/leads`, `/dashboard`, `/relatorios` etc.
- `Atlas, resuma esse lead` volta a exigir um lead aberto ou `context.lead_code`.
- O teste antigo `test_bridge_requires_lead_for_lead_actions` volta a passar.

## Arquivo alterado

- `atlas/copilot/business_lab.py`

## Validação recomendada

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q tests\test_atlas_copilot_bridge.py tests\test_atlas_copilot_screen_summary_hotfix.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```
