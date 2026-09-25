# Sprint 27 - Etapa 10 - Retail + Office Simulation

## Objetivo

Adicionar dois laboratorios empresariais sinteticos ao Atlas Benchmark:

- Retail Lab: estoque, divergencias de preco, pedidos de fornecedor e relatorios.
- Office Lab: e-mails, relatorios, planilhas, agenda e organizacao de arquivos.

Os numeros sao premissas sinteticas e nao representam economia, receita, SLA ou reducao de quadro garantidos.

## Mini frontend

Os dois simuladores exportam payloads JSON estaveis (`schema_version=1.0`) por meio de:

- `retail_dashboard_payload()`
- `office_dashboard_payload()`

Esses contratos serao consumidos pelo mini frontend planejado para a Etapa 12.

## Suite

Execute:

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run retail_office --version 1.0.0
```

Resultado esperado: 10/10 PASS.

## Seguranca e privacidade

A etapa nao altera estoque, ERP, arquivos corporativos ou agenda real. Todos os eventos e tarefas sao sinteticos e usam identificadores `RT-SIM-*` e `OF-SIM-*`.
