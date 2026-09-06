# Sprint 27 — Etapa 2 — Metrics + Resource Monitor

Esta etapa adiciona telemetria padronizada ao Atlas Benchmark sem acoplar o
motor de benchmark ao frontend ou ao kernel operacional.

## Entregas

- Estatísticas de latência: min, média, p50, p95, p99 e máximo.
- Monitor de CPU/RAM do processo Atlas e do sistema via psutil, quando disponível.
- GPU NVIDIA opcional via `nvidia-smi`, sem nova dependência obrigatória.
- VRAM medida no nível da GPU, importante porque o Ollama pode ser o processo
  que mantém o modelo carregado.
- Integração automática das métricas em cada `CaseResult`.
- Flags de CLI para desligar telemetria ou ajustar intervalos.
- Saída de console mostrando CPU, RAM, VRAM e percentis de latência.

## Novas variáveis opcionais

```env
ATLAS_BENCHMARK_RESOURCE_INTERVAL_MS=100
ATLAS_BENCHMARK_GPU_INTERVAL_MS=1000
```

## Comando

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run foundation --version 1.0.0
```

Para medir somente a execução funcional, sem monitoramento:

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run foundation --version 1.0.0 --no-resources
```
