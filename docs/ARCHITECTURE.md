# Arquitetura técnica do Atlas

## Visão geral

O Atlas usa uma arquitetura modular. O `AtlasApp` controla o ciclo de entrada e
saída, enquanto o `AtlasController` é o ponto central para agendamento,
planejamento e execução.

```mermaid
flowchart TD
    U[Usuário] --> A[AtlasApp ou Interface]
    A --> G[AtlasGuiService]
    A --> C[AtlasController]
    API[API local] --> O[Observabilidade e auditoria]
    API --> G
    G --> C
    C --> S[Scheduler]
    C --> P[Planner]
    P --> B[WorkflowBuilder]
    B --> W[WorkflowEngine]
    W --> T[TaskManager]
    W --> E[Executor]
    E --> X[AutomationEngine]
    X --> N[Navegador e Windows]
```

## Componentes principais

| Componente | Responsabilidade |
| --- | --- |
| `atlas/core/app.py` | Entrada por voz/texto, resposta e ciclo da aplicação |
| `atlas/core/kernel.py` | Instancia e conecta as dependências |
| `atlas/core/controller.py` | Orquestra agendamento, planejamento e workflows |
| `atlas/gui/service.py` | Adapta o núcleo para a interface sem duplicar regras |
| `atlas/gui/window.py` | Exibe conversa, estado, métricas e controles |
| `atlas/api/` | Expõe contratos HTTP locais e versionados |
| `atlas/planner/` | Converte linguagem natural em ações estruturadas |
| `atlas/agents/` | Registra e seleciona agentes por domínio e prioridade |
| `atlas/workflow/` | Executa etapas, condições, retries e cancelamento |
| `atlas/planner/task_manager.py` | Controla o ciclo de vida das tarefas |
| `atlas/planner/executor.py` | Executa ações e padroniza resultados |
| `atlas/automation/` | Implementa ações reais no navegador e Windows |
| `atlas/scheduler/` | Analisa, persiste e dispara tarefas agendadas |
| `atlas/context/` | Mantém contexto recente da conversa |
| `atlas/memory/` | Persiste memória local em SQLite |
| `atlas/reasoning/` | Decide entre executar, perguntar e conversar |

## Fluxo de execução imediata

1. `AtlasApp` recebe e normaliza o comando.
2. `AtlasController` verifica se o comando é um agendamento.
3. `Planner` produz uma lista de `Action`.
4. `WorkflowBuilder` converte ações em `WorkflowStep`.
5. `WorkflowEngine` cria tarefas e executa cada etapa.
6. `Executor` chama o `AutomationEngine`.
7. Resultados são devolvidos ao `AtlasApp` e registrados no contexto.

## Agentes especializados

Todo agente implementa o contrato `SpecializedAgent`, declara um
`AgentMetadata` e retorna apenas objetos `Action`. O `AgentRegistry` mantém o
catálogo, aplica prioridade determinística, permite restringir candidatos e
isola falhas não bloqueantes.

O Planner continua responsável pela ordem global do planejamento, mas não
precisa conhecer os detalhes internos de cada novo domínio. Os agentes atuais
são:

| Agente | Domínios principais | Prioridade |
| --- | --- | ---: |
| Browser Agent | navegador, web e pesquisa | 300 |
| RH Agent | recrutamento, seleção e comunicação | 280 |
| IT Help Desk Agent | suporte, diagnóstico e infraestrutura | 275 |
| Sales Agent | vendas, atendimento comercial e leads | 250 |
| Coding Agent | código, desenvolvimento e projeto | 200 |
| Desktop Agent | desktop, Windows e aplicações | 100 |

## Fluxo de agendamento

1. `SchedulerParser` extrai comando, horário e recorrência.
2. `Scheduler` persiste um `ScheduledJob`.
3. `SchedulerWorker` identifica tarefas vencidas.
4. A tarefa retorna ao mesmo `AtlasController`, evitando pipelines paralelos.

## Cancelamento

O cancelamento é cooperativo e centralizado:

- `CancellationToken` guarda estado e auditoria;
- `WorkflowContext` compartilha o token;
- `WorkflowState` registra a etapa cancelada;
- `WorkflowEngine` verifica o token entre operações e retries;
- `AtlasController.cancel_active_workflow()` cancela a execução ativa;
- `TaskManager` marca a tarefa ativa como cancelada.

## Estado persistente

| Pasta | Conteúdo |
| --- | --- |
| `data/` | memória, última sessão e auditoria da API |
| `atlas_data/` | banco JSON do Scheduler |
| `logs/` | log operacional |

Essas pastas são estado local e não fazem parte do código-fonte distribuível.

## Compatibilidade e legado

Os arquivos vazios `atlas/actions/files.py`, `system.py` e `windows.py`, além de
`atlas/core/commands.py`, não participam do fluxo principal atual. Eles foram
mantidos temporariamente para evitar quebrar importações externas. Novas ações
devem ser implementadas em `atlas/automation/` e registradas no
`AutomationEngine`.

`main.py` inicia o modo principal por voz/texto no terminal. `gui_main.py`
inicia a interface gráfica conectada ao mesmo `AtlasController`.

## API local

`api_main.py` inicia um processo HTTP independente em `127.0.0.1`. Os endpoints
de saúde, versão e status permanecem leves: não instanciam `AtlasKernel`,
navegador, microfone, memória ou modelo de linguagem. O núcleo operacional é
carregado de forma preguiçosa somente no primeiro `POST /commands`.

Os comandos passam pelo mesmo `AtlasGuiService`, `AtlasController` e
`WorkflowEngine` utilizados pela interface gráfica. Um executor persistente de
uma única thread mantém criação, execução e encerramento do núcleo na mesma
thread. Essa decisão preserva a afinidade exigida pelo Playwright e permite
reutilizar a sessão do navegador em comandos consecutivos.

O runtime aceita apenas um comando por vez. Uma tentativa concorrente recebe
HTTP `409`; se a espera HTTP ultrapassar o limite configurado, a resposta é
`504`, mas o comando continua no núcleo até terminar ou ser cancelado. O valor
é configurado por `ATLAS_API_COMMAND_TIMEOUT`.

O contrato público começa em `/api/v1`. Mesmo com autenticação, a exposição
fora da máquina local permanece bloqueada até existirem transporte seguro,
rotação de credenciais e controles de implantação.

### Autenticação e autorização

Os endpoints operacionais usam uma chave no cabeçalho `X-API-Key`. A comparação
do segredo ocorre em tempo constante, chaves curtas são rejeitadas e a chave
nunca é devolvida pela API. O endpoint `/auth/me` informa apenas a identidade,
o papel e os escopos associados.

Existem dois perfis locais:

| Papel | Finalidade | Permissões |
| --- | --- | --- |
| `admin` | Operação completa do Atlas | status, comandos, workflows e auditoria |
| `monitor` | Dashboard somente de leitura | consulta de status |

Se nenhuma chave estiver configurada, os endpoints protegidos falham de forma
segura. `health` e `version` permanecem públicos para diagnóstico básico.

O endpoint `POST /api/v1/commands` exige o escopo `commands:execute`, disponível
somente para a chave administrativa. A chave de monitoramento recebe HTTP
`403`, mesmo sendo válida.

### Workflows e auditoria

Cada comando submetido pela API recebe um identificador que também representa
o workflow. O runtime mantém uma visão recente em memória para consultas de
estado e permite solicitar cancelamento cooperativo enquanto a execução está
ativa.

A trilha de auditoria é independente dessa visão em memória e persiste em
SQLite. Ela registra autenticações, submissões, resultados observados, timeouts
e cancelamentos. Conteúdo potencialmente privado é convertido em impressão
SHA-256 e tamanho antes da persistência. O banco nunca recebe a chave de API,
o comando completo, a resposta gerada ou o motivo completo do cancelamento.

Somente o papel `admin`, por meio do escopo `audit:read`, pode consultar os
eventos sanitizados. A aplicação limita a retenção por quantidade e idade,
restringe cabeçalhos `Host` à máquina local, desabilita cache nas respostas da
API e adiciona cabeçalhos contra interpretação indevida de conteúdo e uso em
frames.
