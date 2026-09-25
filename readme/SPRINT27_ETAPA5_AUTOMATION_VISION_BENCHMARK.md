# Sprint 27 — Etapa 5 — Automation + Vision Benchmark

Esta etapa amplia o Atlas Benchmark & Validation Lab para medir automação e
Vision com uma política segura por padrão.

## Escopo

- roteamento de URL explícita sem abrir navegador;
- contrato de falhas do `AutomationEngine`;
- workflow real de arquivos restrito ao diretório temporário do benchmark;
- classificação de comandos Vision read-only, grounding e clique;
- intents estruturadas de texto, formulário, seleção e UIA;
- bloqueio de sequência destrutiva;
- grounding visual sintético com coordenadas conhecidas;
- pós-verificação de efeito de clique;
- captura sintética da tela;
- captura real read-only com `--live`;
- análise multimodal local real com `--live`.

A execução padrão não abre páginas, não move o mouse, não digita, não fecha
janelas e não executa ações destrutivas. O único workflow operacional manipula
arquivos dentro do scratch temporário criado pelo próprio benchmark.

## Suite

Arquivo: `benchmarks/suites/automation_vision.json`

Execução local segura:

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run automation_vision --version 1.0.0
```

Resultado esperado: 8 casos avaliados, 8 PASS e 3 SKIP.

Execução live read-only:

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run automation_vision --version 1.0.0 --live
```

Resultado ideal: 11 casos avaliados e 11 PASS.

O caso `vision.live_analysis` captura a tela atual, envia a imagem somente ao
endpoint loopback/local configurado no Ollama e remove a captura em seguida. O relatório
do benchmark armazena apenas métricas (dimensão, contagens, confiança e modelo),
não o texto visível da tela nem a imagem capturada.

## Métricas iniciais

A etapa registra, entre outras:

- precisão do parser de URLs diretas;
- contrato de `unknown_action`, `missing_parameter` e `invalid_parameter`;
- sucesso do workflow de arquivos isolado;
- precisão do roteamento de intents Vision;
- segurança de sequências estruturadas;
- acerto do grounding em cenário conhecido;
- evidência pós-ação;
- latência de captura real;
- latência da análise visual local;
- CPU, RAM e VRAM via Resource Monitor da Etapa 2.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q atlas\tests\test_benchmark_automation_vision_executors.py
```

A Etapa 5 adiciona 12 testes unitários específicos.
