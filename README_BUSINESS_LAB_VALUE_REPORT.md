# Atlas — Etapa 14.2

## Relatório Atlas x Operação Manual

Esta etapa transforma o benchmark real do Business Lab em um relatório de valor.

Ela mantém a separação correta entre:

- `MEASURED_IN_LOCAL_BUSINESS_LAB`: tempo medido do Atlas executando a API local.
- `ESTIMATED_MANUAL_BASELINE`: tempo manual estimado para uma pessoa executar a mesma tarefa.
- `MEASURED_ATLAS_PLUS_ESTIMATED_MANUAL_BASELINE`: relatório comparativo gerado a partir das duas fontes.

## Arquivos adicionados

```text
atlas/integrations/business_lab/value_report.py
tools/run_business_lab_value_report.py
tests/test_business_lab_value_report.py
README_BUSINESS_LAB_VALUE_REPORT.md
```

## Rodar teste unitário

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q tests\test_business_lab_value_report.py
```

## Gerar relatório

Rode primeiro o benchmark real, se ainda não tiver rodado:

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_benchmark.py
```

Depois gere o comparativo:

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_value_report.py
```

Com estimativa financeira opcional:

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_value_report.py --hourly-cost 25 --monthly-runs 100
```

## Saída

Os relatórios são salvos em:

```text
data\business_lab_benchmark
```

Arquivos gerados:

```text
business_lab_value_report_YYYYMMDD_HHMMSS.json
business_lab_value_report_YYYYMMDD_HHMMSS.csv
business_lab_value_report_YYYYMMDD_HHMMSS.md
```

## Observação

Este relatório ainda não é um case real de cliente. Ele é uma medição local
controlada usando o Business Lab e uma linha de base manual estimada. Isso é o
correto para vender com honestidade: primeiro medição local, depois piloto real.
