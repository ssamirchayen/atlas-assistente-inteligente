# Sprint 27 — Etapa 11 — ROI + Productivity Engine

## Objetivo

Consolidar School Lab, Help Desk + Provisioning, Retail e Office em uma visão comparável de produtividade, mantendo três classes de evidência separadas:

1. **Measured** — histórico técnico realmente medido pelo Atlas Benchmark (latência, score, recursos etc.).
2. **Simulated** — workload e capacidade calculados a partir dos cenários sintéticos dos laboratórios empresariais.
3. **Economic projection** — valor potencial da capacidade humana liberada, calculado por `horas liberadas × custo/hora`.

O motor não converte automaticamente benchmark técnico em promessa comercial e não trata capacidade liberada como redução garantida de folha, caixa ou headcount.

## Suíte

`benchmarks/suites/roi_productivity.json`

Casos:

- `roi.lab_normalization`
- `roi.productivity_math`
- `roi.economic_projection`
- `roi.provenance_separation`
- `roi.measured_history`
- `roi.sensitivity`
- `roi.frontend_contract`

## Contrato para o mini frontend

A saída `portfolio_dashboard_payload()` entrega:

- visão consolidada do portfólio;
- cards por laboratório;
- produtividade manual x Atlas;
- throughput;
- automação e intervenção humana;
- redução de tempo de resposta;
- projeção econômica mensal/anual;
- histórico técnico medido em bloco separado;
- disclaimer e proveniência dos números.

O payload já deixa prontos os tabs `overview`, `school`, `helpdesk`, `retail` e `office` para a Etapa 12.

## Execução

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run roi_productivity --version 1.0.0
```

Resultado esperado: **7/7 PASS**.

## Validação específica

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
atlas\tests\test_benchmark_roi_productivity.py `
atlas\tests\test_benchmark_roi_executors.py
```

Resultado esperado: **9 passed**.

## Segurança de interpretação

Todos os resultados empresariais permanecem sintéticos. O histórico técnico medido pode ser exibido no dashboard, porém possui `used_in_roi=false`. Projeções monetárias representam apenas valor potencial de capacidade reutilizável sob as premissas declaradas.
