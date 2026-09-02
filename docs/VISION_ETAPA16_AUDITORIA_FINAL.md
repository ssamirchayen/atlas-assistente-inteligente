# Atlas Vision — Etapa 16: Auditoria e Fechamento

## Auditoria redigida

Os novos fluxos registram somente:

- instante UTC;
- tipo da operação;
- sucesso ou falha;
- `reason_code`;
- quantidade de ações;
- duração em milissegundos;
- tipo de contexto (`dom`, `uia` ou `none`).

Não são armazenados comandos, textos preenchidos, URLs, tokens, fingerprints,
nomes de campos ou conteúdo visual. O arquivo local padrão é
`data/vision/audit.jsonl`, já excluído do versionamento e do ZIP público.

## Laboratório

Use `tools/vision_supervised_lab.html` para validar checkbox, radio, seleção e
confirmação final sem rede. O formulário apenas altera o título e o status da
página local.

## Resultado do ciclo

Com as Etapas 13–16, o ciclo Vision estruturado fica concluído: percepção e
grounding continuam separados da execução; ações usam DOM/UIA; efeitos são
pós-verificados; ações finais exigem confirmação; e falhas têm recuperação
limitada e auditável.

