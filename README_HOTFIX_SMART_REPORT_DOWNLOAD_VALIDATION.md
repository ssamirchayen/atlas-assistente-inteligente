# Hotfix — Validação de downloads do relatório inteligente

Este hotfix corrige a validação final da Sprint 28.17.

O validador estava esperando o formato antigo:

```text
files.json / files.csv / files.md / files.html / files.xlsx
```

Mas o Smart Reports atual retorna os downloads no formato usado pelo painel do Lab:

```text
files.downloads[]
```

Agora a validação aceita os dois formatos:

- formato antigo dos testes unitários;
- formato atual usado pelo Atlas Bridge e pelo widget do Business Lab.

## Arquivo alterado

```text
atlas/copilot/operation_scale_validation.py
```

## Teste recomendado

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q tests\test_atlas_copilot_operation_scale_validation.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

Depois rode novamente:

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_operation_scale_validation.py
```

O esperado agora é:

```text
Resultado: APROVADO
Etapas: 10/10
```
