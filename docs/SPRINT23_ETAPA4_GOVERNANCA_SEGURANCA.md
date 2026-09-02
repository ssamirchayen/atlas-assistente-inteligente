# Sprint 23 — Etapa 4: Governança, permissões e segurança

## Objetivo

Colocar uma camada central de autorização antes do planejamento, aprovação,
fila, execução, cancelamento e leitura da auditoria do Atlas Edge. Os serviços
das Etapas 2 e 3 continuam responsáveis por reconstruir o plano e executar a
receita; a nova fachada governada decide quem pode solicitar cada operação.

## Funções corporativas

| Função | Capacidades |
| --- | --- |
| `auditor` | listar perfis e tarefas; consultar a auditoria da própria empresa |
| `operator` | preparar plano, colocá-lo na fila, listar e cancelar tarefa aguardando |
| `approver` | revisar e aprovar plano solicitado por outra pessoa |
| `executor` | executar ou cancelar tarefa já aprovada |
| `admin` | administrar o fluxo, sem ignorar allowlists ou isolamento |

Trocar o nome da função no pedido não concede acesso. O `EdgePrincipal` deve
ser produzido por uma camada autenticada da empresa; o Atlas recebe uma função
já validada e a compara com a política local.

## Separação de responsabilidades

1. Um `operator` solicita o perfil.
2. Um `approver` diferente autoriza o plano.
3. O `operator` transfere a autorização de uso único à fila.
4. Um `executor` diferente do aprovador inicia a tarefa.
5. Cada decisão e resultado recebe um evento de auditoria.

O identificador das pessoas vira SHA-256 antes de entrar no plano, na fila ou
na auditoria. Referência do funcionário, e-mail, nome, senha, token e parâmetros
de configuração não são gravados na tabela de auditoria.

## PolicyEngine e allowlists

Cada organização possui sua própria `EdgeOrganizationPolicy`, criada a partir
dos perfis revisados pela TI. Ela limita:

- IDs de perfis;
- IDs exatos de pacotes WinGet;
- IDs e tipos de configurações gerenciadas;
- primeira pasta permitida dentro do workspace corporativo;
- quantidade máxima de etapas;
- autorização explícita para execução real.

O planner continua sem aceitar scripts. Além disso, o PolicyEngine bloqueia
chaves como `command`, `shell`, `powershell`, `script`, `password`, `secret` e
`token`. Pastas como `Windows`, `System32`, `Program Files`, `Users`, `.git`,
`.venv`, `atlas`, `data` e `logs` são protegidas mesmo quando aparecem dentro de
um caminho relativo.

## Isolamento entre organizações

O principal, o dispositivo, a política, o plano e a tarefa devem ter o mesmo
`organization_id`. Uma divergência produz `cross_organization_denied` antes de
consultar ou alterar o recurso. A auditoria SQLite somente retorna eventos da
organização explicitamente consultada.

## Auditoria e LGPD

O arquivo padrão fica em:

```text
data/edge/audit.db
```

Cada evento contém somente horário, organização, dispositivo aleatório, hash do
ator, função, ação, decisão, código de resultado, ID operacional seguro, digest
do plano e indicador de dry-run. Não existe coluna de metadados livres.

Retenção e quantidade são limitadas:

```env
ATLAS_EDGE_AUDIT_RETENTION_DAYS=90
ATLAS_EDGE_AUDIT_MAX_EVENTS=10000
```

Se a auditoria não puder registrar a autorização antes de uma mutação, a ação
falha fechada. Tokens continuam apenas em memória e segredos corporativos devem
ser fornecidos por um cofre externo ao código e aos perfis.

## Execução real

O padrão permanece:

```env
ATLAS_PROVISIONING_DRY_RUN=1
ATLAS_EDGE_EXECUTION_ENABLED=0
```

Alterar somente uma variável não libera mudanças reais. Mesmo com ambas
liberadas, o perfil precisa estar na allowlist, a política da organização deve
permitir execução real, o ator precisa ser `executor` ou `admin`, o executor
deve ser diferente do aprovador e o plano é reconstruído antes de aplicar.

## Piloto seguro

```powershell
.\.venv\Scripts\python.exe edge_governance_pilot.py
```

Digite `SIM` nas três confirmações. O piloto usa inventário sintético, pasta
temporária, auditoria em memória e dry-run. Ele deve terminar com:

```text
Piloto concluído. Nenhum programa ou configuração foi alterado.
```
