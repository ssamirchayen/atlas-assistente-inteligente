# Atlas — Sprint 28.16.1
## Downloads de relatórios inteligentes pelo Business Lab

Esta etapa permite que o relatório gerado pelo Atlas seja baixado diretamente
pelo painel Atlas dentro do Nexyra Business Lab.

## O que entrou

- O Atlas salva automaticamente relatórios inteligentes em JSON, CSV, Markdown e HTML.
- O Atlas Copilot Bridge expõe downloads locais em `/api/copilot/reports/<arquivo>`.
- Os links são locais e servidos por `127.0.0.1:8765`.
- O arquivo CSV pode ser aberto no Excel como planilha.
- O endpoint só libera arquivos com prefixo seguro `business_lab_smart_report`.

## Pasta padrão

```text
C:\Atlas_OFICIAL\data\business_lab_benchmark
```

Também é possível mudar a pasta com:

```powershell
$env:ATLAS_SMART_REPORT_OUTPUT_DIR="C:\Atlas_OFICIAL\data\business_lab_benchmark"
```

## Teste

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q tests\test_atlas_copilot_report_downloads.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

## Uso pelo painel do Lab

Com Business Lab e Atlas Bridge abertos, peça:

```text
Atlas, gere um relatório completo dos leads, matrículas, atendimentos e retornos desta semana.
```

A resposta do Atlas terá botões de download no painel do Lab.
