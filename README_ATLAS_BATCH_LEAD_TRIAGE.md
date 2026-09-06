# Atlas — Sprint 28.13

## Triagem em lote de leads

Esta etapa adiciona ao Atlas Copilot a capacidade de analisar vários leads do Nexyra Business Lab ao mesmo tempo.

O objetivo é sair do uso individual, lead por lead, e começar a demonstrar economia real de tempo em escala.

## O que entrou

- Detecção de comandos de triagem em lote.
- Filtro automático por curso, status, prioridade e quantidade.
- Busca de leads via Integration Framework.
- Ranqueamento dos leads mais importantes.
- Sugestão de próxima ação por lead.
- Resumo seguro para o painel do Copilot.
- Modo prévia: nenhuma ação em lote é executada sem confirmação humana.

## Exemplo no widget

Abra a lista de leads no Business Lab e digite no painel Atlas:

```text
Atlas, analise os 10 leads novos de Radiologia, priorize os mais importantes e sugira a próxima ação para cada um.
```

Outros comandos:

```text
Atlas, faça uma triagem em lote dos leads pendentes.
Atlas, analise os 20 leads de prioridade alta e monte um plano de atendimento.
Atlas, analise os leads de Radiologia que precisam de retorno.
```

## Segurança

Esta etapa ainda não registra atendimentos nem cria retornos em massa.
Ela gera uma prévia segura para revisão humana.

As ações em massa ficam para as próximas etapas:

- 28.14 — Atendimentos e mensagens em lote.
- 28.15 — Execução em escala do sistema inteiro.
- 28.16 — Relatórios inteligentes.
- 28.17 — Validação final da operação em escala.
