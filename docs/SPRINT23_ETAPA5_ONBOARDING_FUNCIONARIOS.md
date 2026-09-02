# Sprint 23 — Etapa 5: Onboarding completo de funcionários

## Objetivo

Unir os componentes das Etapas 1–4 em um workflow único para configurar o
computador de um novo funcionário. O fluxo mantém o estado operacional entre
reinícios, sem persistir o nome do funcionário, tokens de aprovação,
autorizações transitórias, credenciais ou comandos livres.

## Fluxo completo

1. Um operador escolhe um perfil revisado pela TI.
2. O Atlas captura o inventário e gera o plano.
3. Um aprovador diferente revisa e autoriza.
4. O operador transfere a autorização de uso único à fila.
5. Um executor diferente do aprovador inicia a tarefa.
6. Perfil, inventário e etapas são reconstruídos e comparados.
7. O resultado atualiza o onboarding e a auditoria.
8. Um auditor consulta o relatório da própria organização.

Estados possíveis:

| Estado | Significado |
| --- | --- |
| `awaiting_approval` | plano aguardando responsável diferente |
| `authorized` | plano aprovado, ainda fora da fila |
| `queued` | tarefa persistente pronta para execução |
| `running` | execução supervisionada em andamento |
| `action_required` | autorização transitória perdida; novo plano necessário |
| `simulated` | workflow concluído em dry-run |
| `succeeded` | execução real concluída |
| `failed` | falha controlada registrada |
| `cancelled` | workflow cancelado antes da conclusão |

## Persistência e privacidade

O arquivo fica em:

```text
data/edge/onboardings.json
```

Ele contém apenas:

- ID aleatório do onboarding;
- organização e dispositivo;
- hash da referência do funcionário e do solicitante;
- perfil, digest do plano, `task_id` e `evidence_id`;
- estado, revisão, horários e códigos de resultado seguros.

Não existem campos para token, `authorization_id`, nome, e-mail, senha,
servidor, impressora ou parâmetros do perfil. A gravação é atômica, limitada a
1 MiB e usa permissão local restrita quando suportada pelo sistema operacional.

## Continuidade após reinício

Tokens de aprovação e recibos de autorização ficam somente em memória:

- reinício em `awaiting_approval` ou `authorized`: muda para
  `action_required`, e o operador precisa gerar um novo plano usando a mesma
  referência do funcionário;
- reinício em `queued` ou `running`: o serviço reconcilia o `task_id` com a
  fila persistente e permite retomada segura;
- tarefa concluída, falha ou cancelada: o resultado terminal é preservado.

Essa regra impede que uma autorização perdida ou antiga seja reconstruída a
partir do disco.

## Operação simultânea

Até 20 onboardings podem ficar ativos por padrão. Cada funcionário possui
token e autorização separados, e uma referência não pode ter dois workflows
ativos no mesmo dispositivo.

```env
ATLAS_EDGE_MAX_ONBOARDINGS=200
ATLAS_EDGE_MAX_ACTIVE_ONBOARDINGS=20
```

Registros terminais antigos são removidos primeiro quando o histórico atinge o
limite. Um registro ativo nunca é descartado automaticamente.

## Relatório operacional

O relatório informa somente contadores:

- total;
- ativos;
- ação necessária;
- simulados;
- concluídos;
- falhas;
- cancelados.

Consulta e reconciliação passam pelo mesmo RBAC e isolamento por organização da
Etapa 4.

## Limite desta sprint

A Sprint 23 entrega o backend local completo e testável do agente de
computadores. Admin Console, instalador `.EXE`, perfis Lite/Standard/Full e
distribuição empresarial pertencem à Sprint 24 — Atlas Core 1.0.

## Piloto seguro

```powershell
.\.venv\Scripts\python.exe edge_onboarding_pilot.py
```

Digite `SIM` nas três confirmações. O piloto usa inventário sintético, pasta
temporária e dry-run. Ele deve terminar com:

```text
Sprint 23 concluída. Nenhum programa ou configuração foi alterado.
```
