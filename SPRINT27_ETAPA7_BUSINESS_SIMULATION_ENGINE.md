# Sprint 27 — Etapa 7 — Business Simulation Engine

Esta etapa cria a fundação genérica para comparar uma operação manual com uma
operação assistida pelo Atlas usando premissas sintéticas explícitas.

## Princípio de segurança comercial

Um `PASS` nesta suíte significa que o modelo matemático e o contrato de dados
funcionam. Não significa que uma empresa real terá aquele percentual de redução.
Os resultados são projeções sintéticas e carregam um aviso explícito de que não
são garantia de economia ou resultado comercial.

## Métricas

- volume por período;
- itens automatizados e itens ainda manuais;
- horas humanas manuais;
- horas humanas no cenário Atlas;
- horas de máquina do Atlas;
- horas humanas potencialmente liberadas;
- redução projetada de tempo humano;
- erros esperados e retrabalho;
- utilização da equipe;
- capacidade operacional projetada;
- valor potencial da capacidade liberada;
- projeção anual.

## Mini frontend

A Etapa 7 já cria `business_presenter.dashboard_payload()` e valida o esquema
`1.0`. Esse contrato será consumido pelo mini frontend do Atlas Benchmark em uma
etapa posterior, evitando acoplar a interface à lógica matemática.

O payload possui seções estáveis para cenário, comparação, operações, economia
e aviso de simulação.

## Suite

`business_foundation` possui 6 casos:

1. contrato das premissas;
2. manual versus Atlas;
3. erros e retrabalho;
4. capacidade operacional;
5. consistência em escala 100/500/2000;
6. contrato de dados do mini frontend.

## Próximo passo

Etapa 8 — School Lead Simulation: leads sintéticos, cursos, canais, horários,
prioridade, classificação, follow-up, distribuição de consultores e comparação
manual versus Atlas.
