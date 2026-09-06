# Atlas — Etapa 15.1 — Comparação Manual x Atlas Medida

Esta etapa cria o primeiro protocolo de comparação entre o Atlas e uma operação humana medida no Business Lab.

## O que entrou

- CSV-modelo para cronometrar a execução manual dos cenários LAB-001 a LAB-010.
- Leitura de tempos manuais preenchidos em CSV.
- Comparação contra o benchmark real do Atlas gerado na Etapa 14.1.
- Relatório JSON, CSV e Markdown.
- Separação clara entre medição do Atlas e medição manual.

## Arquivos

```text
atlas/integrations/business_lab/pilot_comparison.py
tools/run_business_lab_pilot_comparison.py
tests/test_business_lab_pilot_comparison.py
README_BUSINESS_LAB_PILOT_COMPARISON.md
```

## Criar modelo manual

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_pilot_comparison.py --init-template
```

O arquivo será salvo em:

```text
data\business_lab_benchmark\business_lab_manual_pilot_template.csv
```

Preencha a coluna `elapsed_seconds` com o tempo que uma pessoa levou para executar cada LAB.

## Gerar comparação

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_pilot_comparison.py `
  --manual-csv data\business_lab_benchmark\business_lab_manual_pilot_template.csv `
  --hourly-cost 25 `
  --monthly-runs 100
```

## Saídas

```text
business_lab_pilot_comparison_*.json
business_lab_pilot_comparison_*.csv
business_lab_pilot_comparison_*.md
```

## Observação comercial

Este relatório já é mais forte que a estimativa da Etapa 14.2, porque usa tempo manual preenchido por uma pessoa. Ainda assim, como o Business Lab usa dados sintéticos, ele deve ser apresentado como demonstração controlada ou piloto técnico, não como case real de cliente.
