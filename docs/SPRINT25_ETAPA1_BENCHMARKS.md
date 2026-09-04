# Sprint 25 — Etapa 1: Benchmarks do Validation Lab

## Objetivo

Transformar checks automatizados e seguros em medições repetíveis, permitindo
acompanhar latência e consumo local sem executar comandos de shell, automações
de interface ou ações externas.

Este trabalho já estava presente no Atlas quando a sprint de LGPD foi inserida
antes do Atlas Core 1.0. O código não foi alterado; apenas o documento foi
renumerado para preservar o roadmap.

## Métricas

Cada cenário com política de benchmark registra:

- quantidade de iterações e warm-ups;
- latência mínima, máxima, p50 e p95 em milissegundos;
- tempo e percentual de CPU do processo;
- memória inicial, final, pico e crescimento em MiB.

Os valores aparecem no terminal e são preservados nos relatórios JSON e
Markdown.

## Quality gates

Um cenário pode limitar:

- `p50_ms_max`;
- `p95_ms_max`;
- `cpu_percent_max`;
- `memory_delta_mb_max`.

Ultrapassar qualquer orçamento muda o resultado para `FAIL` e faz a CLI
retornar código 1. A política aceita entre 3 e 100 iterações e até 10 warm-ups,
evitando testes acidentalmente ilimitados.

## Segurança

O benchmark apenas repete os checks declarativos já permitidos pelo runner.
Cenários manuais ou planejados nunca são convertidos em automação.

Não há subprocessos, shell, acesso à rede, cliques, teclado, escrita industrial
ou chamada a agentes durante a medição.

## Uso

```powershell
.\.venv\Scripts\python.exe -m atlas_validation run --domain performance
```

```powershell
.\.venv\Scripts\python.exe -m atlas_validation run `
  --execution automated --benchmark --iterations 20 --warmup 2
```

Os relatórios gerados permanecem como evidências locais e não entram no pacote
de entrega.
