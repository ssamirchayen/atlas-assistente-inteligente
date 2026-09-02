# Sprint 23 — Etapa 3: Execução supervisionada e continuidade

## Objetivo

Transformar um plano aprovado na Etapa 2 em uma tarefa local persistente,
retomável e executada somente após nova ação explícita do operador. A etapa
abrange programas, pastas, navegador, impressoras, VPN e rede.

## Fluxo

1. Solicitante escolhe um perfil e um responsável diferente o aprova.
2. A autorização é consumida uma única vez ao entrar na fila.
3. A fila grava somente hashes, IDs, plano declarativo e estado operacional.
4. O operador escolhe um `task_id` e inicia sua execução.
5. Perfil, dispositivo, organização e inventário são revalidados.
6. O planner reconstrói as etapas usando o catálogo oficial.
7. O Atlas compara cada etapa reconstruída com a fila.
8. Somente depois dessa verificação o executor recebe o plano.
9. Evidência sanitizada atualiza a tarefa como simulada, concluída ou falha.

## Retomada após reinício

A fila fica em:

```text
data/edge/tasks.json
```

Escrita é atômica, o arquivo possui limite de 512 KiB e permissões locais
restritas quando o sistema operacional oferece suporte. Estado inválido,
corrompido ou grande demais provoca falha segura.

Se o processo parar com uma tarefa `running`, a próxima inicialização move essa
tarefa novamente para `queued` e incrementa `recovery_count`. Antes de tentar
de novo, inventário e plano são revalidados. Uma instalação que alterou o
inventário durante a interrupção não é repetida silenciosamente.

## Configurações gerenciadas

Perfis revisados podem declarar:

| Tipo | Parâmetros permitidos | Restrições |
| --- | --- | --- |
| Navegador | navegador e página inicial | somente Chrome, Edge ou Firefox; URL HTTPS |
| Impressora | caminho de conexão | somente caminho UNC validado |
| VPN | nome, servidor, túnel e split tunnel | somente IKEv2 ou SSTP; sem credenciais |
| Rede | nome do perfil e modo | somente `dhcp` ou `corporate`; sem senha |

Essas configurações passam por um `ManagedSettingsAdapter` específico da
empresa. O Atlas não aceita PowerShell, scripts, executáveis, argumentos ou
parâmetros extras enviados pelo usuário. O adaptador padrão bloqueia execução
real; testes e piloto usam simulação.

## Liberação de execução real

O padrão é seguro:

```env
ATLAS_PROVISIONING_DRY_RUN=1
ATLAS_EDGE_EXECUTION_ENABLED=0
```

A execução de programas e pastas somente sai do modo simulado quando as duas
configurações forem alteradas conscientemente:

```env
ATLAS_PROVISIONING_DRY_RUN=0
ATLAS_EDGE_EXECUTION_ENABLED=1
```

Mesmo assim, navegador, impressora, VPN e rede continuam bloqueados enquanto a
empresa não instalar um adaptador revisado. Não desligue o dry-run em ambiente
real antes da Etapa 4, que adicionará RBAC, políticas e auditoria ampliada.

## Piloto seguro

```powershell
.\.venv\Scripts\python.exe edge_execution_pilot.py
```

Digite `SIM` nas três confirmações. O piloto usa uma pasta temporária,
inventário sintético e `dry-run`. Deve terminar com:

```text
Piloto concluído. Nenhum programa ou configuração foi alterado.
```
