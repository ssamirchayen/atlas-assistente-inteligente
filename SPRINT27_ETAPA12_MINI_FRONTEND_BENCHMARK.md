# Sprint 27 — Etapa 12 — Mini Frontend do Atlas Benchmark

## Objetivo

Adicionar uma interface PySide6 compacta ao Atlas Benchmark & Validation Lab sem
misturar resultados técnicos medidos com simulações empresariais ou projeções
econômicas.

## Entrypoints

- `benchmark_gui.py`
- `executar_benchmark_gui.bat`

## Interface

A tela possui quatro áreas principais:

1. **Visão geral** — catálogo de suítes e resumo da execução atual.
2. **Impacto empresarial** — School, Help Desk, Retail e Office consolidados.
3. **Resultado atual** — cada caso, duração, status e score.
4. **Histórico** — execuções salvas em `data/benchmark_runs`.

O topo permite escolher a suíte, versão, seed, telemetria de recursos e modo
`LIVE`.

## Segurança do modo LIVE

O frontend inicia em modo seguro. Ao marcar `LIVE`, uma confirmação explícita é
exigida antes da execução. Dependendo da suíte, o modo LIVE pode acionar Ollama,
Edge TTS ou captura local da tela para o Vision benchmark.

## Proveniência

A interface exibe de forma explícita:

- **MEDIDO**: resultados técnicos reais do benchmark;
- **SIMULADO**: carga operacional sintética;
- **PROJEÇÃO ECONÔMICA**: valor potencial da capacidade liberada.

A projeção econômica não é apresentada como economia garantida ou resultado de
cliente real.

## Arquitetura

A etapa adiciona `atlas.benchmark.runtime` como runtime compartilhado entre CLI
e frontend, reduzindo risco de executores diferentes em cada entrada.

`atlas.benchmark.dashboard_model` fica sem dependência de Qt e concentra o
contrato de apresentação e histórico. A janela PySide6 consome esse modelo.
