# Atlas — Sprint 29 / Bloco D: fechamento seguro Nexyra + Atlas

## Objetivo

Fechar o ciclo de ações supervisionadas entre Atlas e Nexyra CRM 1.0 Desktop, garantindo que a confirmação humana não possa atravessar o Planner, não possa ser reutilizada indefinidamente e não gere repetição automática quando o resultado de uma escrita é incerto.

## Entregas

- `sim`/`não` de uma ação Nexyra pendente são interceptados em `route_priority()`, antes do Planner e dos agentes.
- A prévia fica vinculada à ação normalizada pelo CRM e continua sendo revalidada imediatamente antes da escrita.
- Confirmações expiram após **2 minutos**. Prévia expirada é descartada sem chamada de execução.
- Enquanto há prévia pendente, outra ação/consulta não substitui silenciosamente o estado confirmado. O usuário deve confirmar ou cancelar primeiro.
- `não`, `cancelar`, `Nexyra cancelar`, `cancelar Nexyra` e `Nexyra limpar` invalidam a prévia.
- O estado pendente é removido antes da chamada de execução; timeout, conexão interrompida ou resposta incerta nunca geram retry automático.
- A execução direta também rejeita um `NexyraPendingAction` expirado (defesa em profundidade).
- Mensagens de ajuda/diagnóstico foram atualizadas para refletir que ações supervisionadas estão habilitadas.

## Contrato de segurança

1. Atlas solicita uma prévia explícita.
2. Nexyra normaliza e autoriza a prévia.
3. Atlas exibe ação, alvo, resumo e payload.
4. Usuário confirma em até 2 minutos.
5. Atlas reconsulta a prévia no CRM.
6. Fingerprint diferente aborta a operação.
7. Somente então Atlas envia `confirmed: true`.
8. Falha após a tentativa de escrita exige conferência manual do CRM; não há repetição automática.

## Validação

A validação automatizada cobre interceptação antes do Planner, expiração, cancelamento, bloqueio de troca de ação, revalidação, fingerprint, falhas HTTP/rede e ausência de retry. O teste opcional `tests/test_nexyra_crm_contract.py` continua validando o conector contra as rotas reais do CRM via `NEXYRA_CRM_SOURCE`.
