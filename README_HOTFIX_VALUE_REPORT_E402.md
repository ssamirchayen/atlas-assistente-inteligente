# Hotfix — Value Report E402

Corrige o Ruff E402 em `tools/run_business_lab_value_report.py`.

O arquivo agora usa `importlib.import_module` depois de preparar o `sys.path`, evitando import de módulo do Atlas no topo do arquivo de ferramenta.

Arquivos alterados:

```text
tools/run_business_lab_value_report.py
```

Depois de aplicar:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q tests\test_business_lab_value_report.py
```
