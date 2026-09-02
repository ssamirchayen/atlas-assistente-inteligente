# Atlas Vision — Etapa 15: Recuperação Limitada

## Política

A recuperação diferencia falha anterior à ação de falha posterior à ação:

- antes de qualquer efeito, no máximo um retry estrutural pode ser permitido;
- depois que a ação foi enviada, retry é proibido para evitar duplicidade;
- controles booleanos reversíveis podem voltar uma vez ao estado anterior;
- ações finais e demais efeitos irreversíveis nunca recebem rollback automático;
- orçamento de retry esgotado encerra o fluxo com `reason_code` explícito.

Essa política é determinística e testável em `atlas/vision/recovery.py`.

