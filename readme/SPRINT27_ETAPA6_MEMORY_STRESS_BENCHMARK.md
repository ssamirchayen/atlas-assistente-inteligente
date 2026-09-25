# Sprint 27 — Etapa 6 — Memory + Stress Benchmark

Esta etapa amplia o Atlas Benchmark & Validation Lab para medir a memória local
sob uso normal, persistência, concorrência e aumento progressivo de carga.

## Segurança e isolamento

Todos os bancos SQLite desta suite são criados dentro do `scratch_dir`
temporário do próprio benchmark. A memória real do Atlas (`data/memory.db`) não
é aberta, alterada ou copiada.

A busca semântica também fica desativada nesta etapa. Assim, os resultados
medem especificamente o armazenamento SQLite e a busca lexical local, sem
misturar latência de Ollama/embeddings.

## Casos

- `memory.crud_contract`: criar, ler, atualizar, esquecer e restaurar;
- `memory.persistence`: fechar o banco, reabrir e recuperar dados;
- `memory.keyed_upsert`: create/unchanged/update mantendo uma única memória;
- `memory.search_accuracy`: precisão top-1 com tokens sintéticos controlados;
- `memory.concurrent_writes`: gravações concorrentes + `PRAGMA integrity_check`;
- `stress.write_scaling`: lotes de 10, 50, 100 e 500 gravações;
- `stress.search_scaling`: busca com 10, 100 e 500 registros;
- `stress.reopen_cycles`: cinco ciclos de fechamento/reabertura.

## Métricas

Além de CPU/RAM/VRAM do Resource Monitor da Etapa 2, esta suite registra:

- latência média, p95 e máxima por operação;
- gravações por segundo;
- precisão de busca;
- tamanho do banco SQLite;
- integridade do banco;
- tempo de reabertura;
- degradação percentual da latência entre a menor e a maior carga.

A degradação é registrada como dado observacional e **não** reduz o score
funcional nesta etapa. Isso evita classificar hardware diferente como falha.
Uma etapa posterior poderá transformar esses baselines em Performance Score.

## Execução

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run memory_stress --version 1.0.0
```

Resultado esperado: 8 casos avaliados, 8 PASS, 0 FAIL, 0 ERROR e 0 SKIP.

Não é necessário `--live`.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q atlas\tests\test_benchmark_memory_stress_executors.py
```

A Etapa 6 adiciona 9 testes unitários específicos.
