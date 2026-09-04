# Sprint 24 — Etapa 4: retenção e descarte verificável

## Objetivo

Esta etapa transforma prazos aprovados pela organização em decisões técnicas
repetíveis. O Atlas pode identificar se um registro ainda deve ser mantido, se
está em carência, se existe impedimento ou se uma ação de ciclo de vida está
vencida. O motor apenas decide; o coordenador supervisionado prepara e, quando
explicitamente habilitado, executa uma exclusão lógica em um único adaptador.

O componente não escolhe prazo, base legal nem exceção de conservação. Essas
decisões continuam sob responsabilidade do controlador e do encarregado.

## Fluxo de segurança

1. Uma regra versionada e aprovada define evento inicial, prazo, carência e ação.
2. Um candidato pseudonimizado é avaliado no tenant e fluxo exatos.
3. Política ausente, suspensa ou sem data do evento bloqueia o descarte.
4. Um bloqueio legal ativo impede a ação; bloqueios não podem ser indefinidos.
5. O adaptador calcula quantos registros seriam afetados e informa impedimentos.
6. O Atlas cria um plano de 15 minutos, sem copiar o conteúdo dos dados.
7. Duas pessoas diferentes aprovam mutações com `APROVAR <id>`.
8. Um operador autorizado confirma `EXECUTAR <id>`.
9. Política, versão, prazo, bloqueios e adaptador são revalidados.
10. Em `dry-run`, nada muda. Em modo habilitado, o adaptador exclui uma vez.
11. O comprovante contém hashes e contagens, nunca valores pessoais.
12. Operadores compartilhados geram tarefas pendentes para tratamento humano.

## Eventos de retenção

As regras aceitam quatro marcos explícitos:

- criação do registro;
- última atividade;
- conclusão da finalidade;
- revogação do consentimento.

Se o evento escolhido não estiver disponível, a decisão é bloqueada. O sistema
não inventa datas e não usa o horário atual como substituto.

## Ações

- `delete`: possui execução lógica através do contrato `SubjectDataSource`;
- `anonymize`: exige adaptador específico e permanece manual nesta etapa;
- `block`: exige adaptador específico e permanece manual nesta etapa;
- `review`: produz revisão supervisionada, sem modificar dados.

Somente `delete` pode ser executada pelo adaptador atual. Essa limitação evita
que o sistema trate exclusão como anonimização ou bloqueio.

## Bloqueios legais

Um `LegalHold` possui organização, fluxo, motivo estruturado, aprovação, início
e expiração. Ele pode abranger o fluxo ou um titular pseudonimizado. A liberação
registra responsável e horário, e é idempotente.

O bloqueio técnico não afirma que a conservação seja juridicamente válida. O
motivo e o prazo devem ser aprovados e revisados pela organização.

## Comprovante e operadores

O `DisposalReceipt` registra:

- identificadores técnicos do plano, fonte e fluxo;
- hashes do titular pseudonimizado e do executor;
- versão da regra incorporada ao digest do plano;
- ação, horário e quantidade afetada;
- digest de evidência.

Ele não contém nome, telefone, e-mail, conteúdo de conversa ou valor de campo.
Para cada `processor_id` declarado, a execução cria uma
`ProcessorNotificationTask` pendente. Nenhuma chamada de rede é feita; a entrega
real deve ser implementada com autenticação, confirmação e evidência próprias.

## Limites deliberados

- regras são mantidas em memória nesta entrega;
- fontes reais não são conectadas automaticamente;
- execução real começa desativada;
- somente uma fonte é tratada por plano, evitando atomicidade falsa;
- o comprovante prova a chamada lógica do adaptador, não o apagamento físico;
- replicações, snapshots e backups exigem política e procedimento próprios;
- conformidade depende de governança, contratos e avaliação jurídica externa.

## Referências normativas

- Lei nº 13.709/2018 (LGPD), especialmente arts. 15, 16 e 18:
  https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/L13709compilado.htm
- Direitos dos titulares — ANPD:
  https://www.gov.br/anpd/pt-br/assuntos/titular-de-dados-1/direito-dos-titulares
