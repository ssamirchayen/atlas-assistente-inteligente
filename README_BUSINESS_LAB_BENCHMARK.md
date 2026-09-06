# Atlas — Etapa 14.1

## Business Lab Benchmark Runner

Esta etapa adiciona um benchmark real do Atlas contra o Nexyra Business Lab.

O benchmark executa os cenários LAB-001 a LAB-010 pelo Integration Framework,
mede latência, sucesso/falha, driver usado e salva relatórios técnicos em JSON e CSV.

## Importante

- Não usa gabaritos oficiais.
- Não consulta `/api/v1/cenarios`.
- Não declara resultado como cliente real.
- A origem do dado é marcada como `MEASURED_IN_LOCAL_BUSINESS_LAB`.

## Rodar

Com o Business Lab aberto:

```powershell
cd C:\Atlas_OFICIAL

$env:ATLAS_BUSINESS_LAB_URL="http://127.0.0.1:5055"
$env:ATLAS_BUSINESS_LAB_EMAIL="consultor@nexyra.lab"
$env:ATLAS_BUSINESS_LAB_PASSWORD="Consultor123!"

.\.venv\Scripts\python.exe tools\run_business_lab_benchmark.py
```

## Repetir 3 vezes

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_benchmark.py --repeat 3
```

## Rodar cenário específico

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_benchmark.py --scenario LAB-001
```

## Saída

Os relatórios são salvos por padrão em:

```text
data/business_lab_benchmark/
```

Arquivos gerados:

- `business_lab_benchmark_YYYYMMDD_HHMMSS.json`
- `business_lab_benchmark_YYYYMMDD_HHMMSS.csv`
