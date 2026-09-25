# Atlas — Hotfix pytest x tools

Este hotfix impede que o pytest colete scripts da pasta `tools/` como se fossem testes.

## Problema corrigido

Ao rodar:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

o pytest tentava coletar `tools/test_integration_framework.py`, mas já existia
`tests/test_integration_framework.py` com o mesmo nome de módulo. Isso gerava:

```text
import file mismatch
```

## Solução

Adiciona `pytest.ini` na raiz do projeto para limitar a coleta automática de testes
à pasta `tests/`.

Os scripts da pasta `tools/` continuam funcionando normalmente quando chamados
diretamente, por exemplo:

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_lab001.py
```
