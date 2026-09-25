# Atlas — Sprint 29 / Bloco E

## Inteligência Operacional do Nexyra + Atlas

Este bloco mantém duas edições separadas:

- **Nexyra padrão**: standalone, sem dependência do Atlas e sem a rota operacional deste bloco.
- **Nexyra + Atlas**: cópia/edição integrada que adiciona o endpoint operacional consumido pelo Atlas.

## Consultas novas no Atlas

- `Nexyra fila`
- `Nexyra SLA`
- `Nexyra recomendações`
- `Nexyra dashboard`
- `Nexyra equipe`
- `Nexyra operação`

Também são reconhecidas frases naturais como:

- `quais leads eu preciso atender agora`
- `quem está com SLA estourada`
- `quais vendedores estão sobrecarregados`
- `quais oportunidades estão em risco`
- `resuma a operação comercial de hoje`

## Dados consultados

A edição integrada agrega, em uma única chamada segura:

- fila/SLA de leads;
- recomendações comerciais;
- distribuição e carga da equipe;
- dashboard operacional e gargalos.

## Segurança

A rota operacional usa o mesmo token de integração da Sprint 29 e exige:

- `atlas.use` via integração;
- `analytics.read` no usuário ator, portanto gerente ou administrador.

O Atlas continua somente consultando neste bloco. Escritas permanecem no fluxo supervisionado do Bloco D, com prévia, revalidação e confirmação.
