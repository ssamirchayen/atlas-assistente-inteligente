# Sprint 25 — Etapa 3: lazy loading

## Objetivo

O Atlas deixa de construir Brain e Vision durante a inicialização do Kernel.
Esses componentes recebem factories explícitas e são materializados somente no
primeiro comando que utiliza suas interfaces.

Os comandos continuam acessando `kernel.brain.respond(...)` e
`kernel.vision...`; o proxy preserva esse contrato e resolve internamente a
instância compartilhada.

## Estados

| Estado | Significado |
| --- | --- |
| `unloaded` | factory ainda não executada |
| `loading` | uma thread está construindo a instância |
| `ready` | instância única disponível |
| `failed` | inicialização falhou e exige recuperação explícita |

Cada snapshot contém somente nome técnico, estado, tentativas, cargas bem-
sucedidas, duração e tipo da última exceção. A mensagem da exceção não é
armazenada para evitar exposição acidental de caminhos ou dados locais.

## Concorrência

Uma `Condition` protege o ciclo de vida. A primeira thread executa a factory;
as demais aguardam e recebem o mesmo objeto. A factory nunca roda sob o lock de
estado. Uma tentativa recursiva na mesma thread gera erro explícito em vez de
deadlock.

## Falhas e recuperação

Uma falha é armazenada por tipo e não é repetida automaticamente. Isso impede
loops de inicialização quando uma dependência está ausente. `reset_failure()`
permite uma nova tentativa explícita, mas nunca descarrega uma instância pronta.

## Integração

- imports de Brain e Vision foram movidos para factories locais;
- `AtlasKernel` registra ambos em `lazy_components`;
- `Planner` recebe o mesmo proxy usado pelo Core;
- `IntelligentPlanner` mantém criação própria apenas quando usado isoladamente;
- `AutomationEngine` recebe uma função que resolve o Brain somente ao responder;
- GUI, voz, API e automações mantêm os contratos existentes.

## Limites deliberados

- voz e memória continuam essenciais e são carregadas no início;
- o primeiro uso de cada componente ainda paga seu custo de inicialização;
- nenhum componente pronto é descarregado nesta etapa;
- preload existe apenas por chamada explícita do registro;
- o piloto não carrega modelos ou realiza captura real;
- medição comparativa de startup no Windows continua no Validation Lab.
