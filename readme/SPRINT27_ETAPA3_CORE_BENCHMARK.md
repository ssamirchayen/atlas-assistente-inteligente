# Sprint 27 — Etapa 3 — Atlas Core Benchmark

Esta etapa inicia os benchmarks reais do Atlas Core sobre a infraestrutura
criada nas Etapas 1 e 2.

## Cobertura

- imports críticos do Core;
- normalização de texto e remoção de wake word;
- semântica de lazy loading;
- seleção do Runtime Profile no hardware atual;
- classificação e roteamento determinístico do Model Router;
- disponibilidade do Ollama e do modelo configurado (opt-in `--live`);
- resposta real do Ollama com probe determinístico (opt-in `--live`).

Os casos locais são seguros e não dependem do Ollama. Os casos live ficam como
`SKIP` quando `--live` não é informado.

## Execução local

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run core --version 1.0.0
```

## Execução real com Ollama

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run core --version 1.0.0 --live
```

Timeout do probe de chat:

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run core --version 1.0.0 --live --ollama-timeout 120
```
