# Atlas — Etapa 14.4 — Demo Pack Comercial

Esta etapa consolida os relatórios gerados nas etapas 14.1, 14.2 e 14.3 em um pacote único de demonstração.

## Arquivos adicionados

```text
atlas/integrations/business_lab/demo_pack.py
tools/run_business_lab_demo_pack.py
tests/test_business_lab_demo_pack.py
README_BUSINESS_LAB_DEMO_PACK.md
```

## O que ela gera

- Pasta `atlas_business_lab_demo_pack_YYYYMMDD_HHMMSS`.
- ZIP comercial com os relatórios principais.
- Manifesto de rastreabilidade.
- `LEIA_ME.md` com instruções de uso.
- Relatório executivo HTML pronto para abrir no navegador.
- Relatórios JSON/CSV/MD para auditoria e conferência.

## Pré-requisitos

Antes, rode as etapas anteriores:

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_benchmark.py
.\.venv\Scripts\python.exe tools\run_business_lab_value_report.py --hourly-cost 25 --monthly-runs 100
.\.venv\Scripts\python.exe tools\run_business_lab_executive_report.py
```

## Uso

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_demo_pack.py
```

Com parâmetros comerciais:

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_demo_pack.py `
  --company-name "Nexyra" `
  --product-name "Atlas" `
  --client-segment "escola técnica / CRM educacional"
```

## Saída

Os arquivos serão salvos em:

```text
data\business_lab_benchmark
```

## Observação de confiança

O pacote é apropriado para demonstração técnica/comercial, mas mantém aviso explícito de que os dados são sintéticos e que o resultado ainda não é um case real de cliente em produção.
