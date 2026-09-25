# Sprint 27 — Etapa 1 — Atlas Benchmark Engine

Esta etapa cria a fundação do **Atlas Benchmark & Validation Lab** sem alterar
o Kernel, a GUI, a voz ou as automações operacionais.

## O que entrou

- `atlas/benchmark/models.py`: modelos comuns para benchmark técnico e
  simulação empresarial.
- `atlas/benchmark/catalog.py`: carregamento de suites declarativas em JSON.
- `atlas/benchmark/runner.py`: execução isolada, captura de falhas, score
  ponderado e seed determinística.
- `atlas/benchmark/storage.py`: histórico local em JSON, salvo por padrão em
  `data/benchmark_runs` (já protegido pelo `.gitignore` do Atlas).
- `atlas/benchmark/report.py`: relatório de console inicial.
- `atlas/benchmark/builtins.py`: executores seguros usados apenas para validar
  a própria fundação.
- `benchmarks/suites/foundation.json`: primeira suite oficial.
- `tools/run_atlas_benchmark.py`: CLI do novo laboratório.
- testes unitários da fundação.

## Relação com o Validation Lab existente

O `atlas.validation` continua sendo o motor de cenários de validação já
existente. A Sprint 27 não o substitui. O novo `atlas.benchmark` é a camada de
orquestração, pontuação, histórico e futuras simulações empresariais.

Nas próximas etapas serão adicionados adaptadores para transformar cenários do
Validation Lab em casos do Benchmark sem duplicar lógica.

## Validação da Etapa 1

No PowerShell, dentro de `C:\Atlas_OFICIAL`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q atlas/tests/test_benchmark_models.py atlas/tests/test_benchmark_catalog.py atlas/tests/test_benchmark_runner.py atlas/tests/test_benchmark_storage.py
.\.venv\Scripts\python.exe -m ruff check atlas/benchmark tools/run_atlas_benchmark.py atlas/tests/test_benchmark_*.py
```

Depois rode o smoke benchmark:

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run foundation
```

O esperado é:

- 3 casos executados;
- 3 PASS;
- success rate 100%;
- weighted score 100/100;
- um JSON salvo em `data\benchmark_runs`.

Por fim, faça a regressão completa:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

## Segurança

A suite `foundation` é totalmente sintética e não abre navegador, não usa
microfone, não envia WhatsApp e não altera o Atlas operacional. Cada caso recebe
um diretório temporário isolado, descartado ao fim da execução.

## Próxima etapa

**Sprint 27 — Etapa 2 — Metrics + Resource Monitor**

Ela adicionará coleta padronizada de CPU, RAM, VRAM, latência, startup,
percentis e snapshots de recurso, reutilizáveis por todos os benchmarks.
