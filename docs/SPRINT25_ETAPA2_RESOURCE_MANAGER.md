# Sprint 25 — Etapa 2: Resource Manager

## Objetivo

O Resource Manager aplica o limite de tarefas simultâneas preparado pelos perfis
Lite, Standard e Full. Ele mede pressão antes de admitir um novo workflow e
devolve um resultado recuperável quando o computador precisa ser preservado.

O componente atua somente dentro do Atlas. Não enumera processos de terceiros,
não altera prioridade, não encerra programas, não executa comandos e não muda
configurações do Windows.

## Métricas

Cada amostra contém somente:

- percentual agregado de CPU, quando disponível;
- percentual e quantidade disponível de RAM do sistema;
- RSS do processo atual do Atlas, quando disponível;
- horário UTC da medição.

CPU e RSS são opcionais. A impossibilidade de medir RAM interrompe a admissão,
porque aceitar carga sem a métrica essencial seria inseguro.

## Estados de pressão

| Estado | Condição principal | Nova admissão |
| --- | --- | --- |
| Normal | abaixo dos limites | leve, padrão e pesada |
| Alerta | CPU ≥ 90%, RAM ≥ 85% ou disponível ≤ 1,5 GB | leve e padrão |
| Crítico | CPU ≥ 98%, RAM ≥ 95%, disponível ≤ 0,5 GB ou RSS acima do orçamento | somente leve |

Condições simultâneas preservam todos os códigos de motivo. Métricas temporárias
não promovem o perfil da máquina e não alteram o `.env`.

## Licenças

Cada workflow admitido recebe uma licença aleatória. A capacidade é:

- Lite: uma licença;
- Standard: duas licenças;
- Full: quatro licenças.

A aquisição e a liberação são protegidas por lock. O context manager devolve a
licença no sucesso, em falha ou exceção. Uma segunda liberação é idempotente.

## Integração

O `AtlasKernel` cria uma única instância após resolver o perfil e entrega a mesma
instância ao `WorkflowEngine`. Workflows comuns usam classe `standard`; pesquisa
na internet e ações de programação são `heavy`; espera controlada é `light`.

Uma recusa produz `ExecutionResult` com:

- `action_type=resource.admission`;
- código de capacidade, pressão ou hardware incompatível;
- estado de pressão e motivos estruturados;
- `retryable=True`.

Hardware abaixo do mínimo usa `retryable=False`; aguardar não corrige essa
condição. Falha temporária da medição essencial usa `rejected_metrics` e pode ser
tentada novamente sem executar a ação original.

Assim o comando não é executado, mas também não desaparece nem cai no fluxo de
conversa como se nunca tivesse sido reconhecido.

## Auditoria

A trilha em memória registra perfil, classe, pressão, motivos, quantidade ativa
e identificador técnico da licença. Ela não guarda comando, parâmetros, nome de
arquivo, usuário ou payload. A coleção possui limite configurável.

## Limites deliberados

- a trilha ainda não possui persistência;
- o Resource Manager não cancela uma operação já admitida;
- pressão controla novas entradas, não recursos de outros aplicativos;
- módulos de voz, visão e modelo ainda serão adaptados ao lazy loading;
- thresholds corporativos configuráveis ficam para uma etapa posterior;
- métricas não substituem benchmark do perfil Lite em VM Windows com 8 GB.
