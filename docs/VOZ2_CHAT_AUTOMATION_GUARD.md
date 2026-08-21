# Voz 2.0 — Chat Automation Guard

Correção de regressão descoberta durante o teste de voz contínua.

## Problema

Uma pergunta conversacional como:

`me explique como funciona uma API e de alguns exemplos`

era corretamente classificada como `CHAT`, mas continuava até o
`IntelligentPlanner`, que podia gerar ações operacionais não solicitadas.

## Correção

- perguntas informativas recebem prioridade como `chat` no `IntentAnalyzer`;
- `Planner` encerra imediatamente o planejamento quando a intenção é `chat`;
- o fluxo superior continua normalmente para `Brain/Ollama`;
- comandos explícitos, como `abra o Chrome`, continuam sendo automação;
- foram adicionados testes de regressão.

## Fluxo esperado

Pergunta -> CHAT -> Planner retorna [] -> Brain/Ollama -> TTS

Comando explícito -> intenção operacional -> Planner -> Workflow -> Executor
