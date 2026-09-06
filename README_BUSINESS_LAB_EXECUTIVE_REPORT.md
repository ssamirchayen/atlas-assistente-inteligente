# Atlas — Etapa 14.3 — Relatório Executivo Comercial

Esta etapa transforma o relatório técnico `Atlas x Operação Manual` em um material executivo para demonstração comercial da Nexyra.

## Arquivos adicionados

```text
atlas/integrations/business_lab/executive_report.py
tools/run_business_lab_executive_report.py
tests/test_business_lab_executive_report.py
README_BUSINESS_LAB_EXECUTIVE_REPORT.md
```

## O que a etapa gera

- JSON estruturado do relatório executivo.
- Markdown pronto para leitura e edição.
- HTML visual para abrir no navegador.
- Resumo comercial com indicadores principais.
- Limitações honestas para evitar promessa falsa.
- Próximos passos para demonstração e piloto seguro.

## Pré-requisito

Antes de rodar esta etapa, gere o relatório de valor da etapa 14.2:

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_value_report.py --hourly-cost 25 --monthly-runs 100
```

## Uso

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_executive_report.py
```

Com parâmetros comerciais:

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_executive_report.py `
  --company-name "Nexyra" `
  --product-name "Atlas" `
  --client-segment "escola técnica / CRM educacional"
```

Os arquivos são salvos em:

```text
data/business_lab_benchmark
```

## Validação

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_business_lab_executive_report.py
.\.venv\Scripts\python.exe -m ruff check .
```

## Observação de confiança

Este relatório usa métricas reais medidas no Business Lab local e uma linha manual estimada. Ele é adequado para demonstração técnica/comercial, mas não deve ser apresentado como ganho real de cliente sem piloto supervisionado.
