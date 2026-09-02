# Atlas Validation Lab

O **Atlas Validation Lab** é a fundação permanente de validação do projeto.
Ele separa três classes de cenário:

- **automated**: verificações determinísticas e seguras executadas pelo runner;
- **manual**: cenários E2E que exigem interação controlada com GUI, voz, browser ou ambiente real;
- **planned**: cenários já especificados para capacidades de sprints futuras.

## Comandos

Listar todos os cenários:

```powershell
C:\Atlas_OFICIAL\.venv\Scripts\python.exe -m atlas_validation list
```

Executar apenas os cenários automatizados:

```powershell
C:\Atlas_OFICIAL\.venv\Scripts\python.exe -m atlas_validation run --execution automated
```

Executar um domínio:

```powershell
C:\Atlas_OFICIAL\.venv\Scripts\python.exe -m atlas_validation run --domain core
```

Gerar relatórios:

```powershell
C:\Atlas_OFICIAL\.venv\Scripts\python.exe -m atlas_validation run --execution automated `
  --json reports/validation.json `
  --markdown reports/validation.md
```

Executar benchmarks seguros em cenários automatizados:

```powershell
C:\Atlas_OFICIAL\.venv\Scripts\python.exe -m atlas_validation run `
  --execution automated --benchmark --iterations 20 --warmup 2
```

Aplicar quality gates de desempenho:

```powershell
C:\Atlas_OFICIAL\.venv\Scripts\python.exe -m atlas_validation run `
  --domain performance --benchmark --iterations 20 `
  --p95-ms-max 50 --memory-delta-mb-max 16
```

## Estrutura de um cenário

Cada cenário registra:

- ID estável;
- domínio;
- modo de execução;
- risco;
- fase/sprint;
- pré-condições;
- passos;
- resultados esperados;
- métricas quando aplicável;
- checks automatizados quando seguros.

## Regra de segurança

O runner **não executa automaticamente ações destrutivas, comandos de shell, cliques, escrita industrial, alterações de VFD/PLC ou automações de alto risco**. Esses fluxos permanecem manuais ou planejados até existir um harness seguro/simulado específico.

Para indústria e demais domínios críticos, a ordem é:

1. dados sintéticos/simulador;
2. bancada isolada;
3. integração read-only;
4. ação assistida com aprovação;
5. somente depois, automação controlada previamente autorizada.

## Evolução da Sprint 24

A Etapa 1 já adiciona:

- benchmark repetível de checks declarativos;
- latência mínima, máxima, p50 e p95;
- tempo/percentual de CPU e memória inicial, final, pico e delta;
- warm-up configurável;
- quality gates para p50, p95, CPU e crescimento de memória;
- métricas nos relatórios de terminal, JSON e Markdown.

Permanecem previstas para as próximas etapas:

- captura de GPU/VRAM quando houver hardware compatível;
- evidências de screenshots/logs;
- execução por perfis Lite/Standard/Full;
- dashboard do Validation Lab na Admin Console;
- histórico de regressão por versão;
- CI com quality gates;
- suites de contrato para Agents e Connectors.
