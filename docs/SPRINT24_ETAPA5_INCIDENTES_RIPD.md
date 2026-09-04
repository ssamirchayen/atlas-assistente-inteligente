# Sprint 24 — Etapa 5: incidentes e RIPD supervisionado

## Objetivo

Esta etapa encerra a fundação técnica da Sprint 24 com dois fluxos de governança:
resposta supervisionada a incidentes de dados pessoais e elaboração estruturada
de Relatório de Impacto à Proteção de Dados Pessoais (RIPD). Ambos falham de
forma segura, registram somente metadados necessários e dependem de decisão
humana nas etapas críticas.

O módulo não substitui o controlador, o encarregado, a equipe de segurança nem a
assessoria jurídica. Ele organiza decisões, prazos, aprovações e evidências.

## Resposta a incidentes

O fluxo registra:

- organização e momento de detecção;
- fluxos do inventário potencialmente atingidos;
- categorias de dados envolvidas;
- propriedades afetadas: confidencialidade, integridade, disponibilidade e
  autenticidade;
- quantidade estimada de titulares e fatores de risco;
- códigos estruturados de impactos potenciais.

Nenhum nome, telefone, e-mail, documento, conteúdo de mensagem ou payload do
incidente é guardado pelo serviço.

### Fluxo supervisionado

1. Um incidente é registrado com identificador aleatório.
2. Um agente autorizado confirma o evento com `CONFIRMAR <id>`.
3. A triagem produz conclusão relevante, não relevante ou indeterminada.
4. Toda conclusão permanece sujeita a revisão humana.
5. Incidentes relevantes recebem um plano de comunicação.
6. O plano valida a presença das informações mínimas documentadas.
7. Duas pessoas diferentes confirmam `APROVAR <id>`.
8. O Atlas cria tarefas manuais para ANPD e titulares afetados.
9. Após o envio humano, são registrados apenas digests das evidências.
10. A repetição do registro devolve o mesmo comprovante e não duplica o evento.

O Atlas não envia e-mail, formulário, mensagem ou requisição de rede nesse fluxo.

### Prazos

O prazo técnico é calculado a partir da confirmação do incidente:

- três dias úteis para a comunicação inicial;
- vinte dias úteis adicionais para complementação quando a comunicação for
  preliminar.

O contador soma somente segunda a sexta. Feriados nacionais, estaduais,
municipais, pontos facultativos, regras setoriais e suspensões precisam de um
calendário externo homologado antes do uso em produção.

## RIPD estruturado

O `ImpactAssessmentService` relaciona o RIPD aos registros existentes no
inventário. O rascunho declara:

- finalidade e operações de tratamento;
- necessidade e proporcionalidade;
- contexto da operação;
- salvaguardas implantadas;
- cenários de risco inerente e residual;
- fluxos do inventário abrangidos.

A avaliação também identifica, a partir do inventário, tratamento de dados
sensíveis, crianças ou adolescentes e transferência internacional.

### Matriz e bloqueios

Probabilidade e impacto usam escala de 1 a 5. O risco residual não pode superar
o risco inerente. Seções vazias, fluxos desconhecidos ou riscos residuais altos
e críticos impedem a aprovação. Um RIPD apto exige duas aprovações distintas de
responsáveis com escopo específico.

O relatório final contém digests do inventário e da avaliação, classificação do
maior risco residual e hashes dos aprovadores. Por projeto, mantém
`legal_conformity_declared=False`: o documento técnico não afirma, sozinho, que
a organização está em conformidade com a LGPD.

## Auditoria e isolamento

Os dois serviços verificam a organização em todas as consultas e mutações. Os
eventos de auditoria usam hashes dos responsáveis e detalhes estruturados. As
coleções em memória têm capacidade limitada e não aceitam conteúdo livre de
dados pessoais como evidência.

## Limites deliberados

- incidentes e RIPDs ainda são mantidos em memória;
- não existe envio automático à ANPD ou aos titulares;
- não existe integração automática com SIEM, central de suporte ou jurídico;
- o calendário não conhece feriados;
- digests demonstram vínculo lógico, não autenticidade jurídica da evidência;
- a matriz auxilia priorização e não substitui metodologia aprovada da empresa;
- modelos, prazos e conteúdo devem ser revisados conforme o caso concreto;
- esta base técnica não é certificação, auditoria jurídica nem parecer legal.

## Requisitos para produção

- armazenamento persistente criptografado e com controle de acesso;
- integração com identidade corporativa e segregação de funções;
- calendário oficial versionado;
- cofre e cadeia de custódia das evidências;
- canais de comunicação homologados, sempre sob autorização humana;
- procedimento de resposta a incidentes testado pela organização;
- modelo de RIPD e critérios de risco aprovados pelo encarregado e pelo jurídico.

## Referências oficiais

- LGPD, especialmente arts. 38, 41 e 46 a 48:
  https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/L13709compilado.htm
- Comunicação de incidente de segurança — ANPD:
  https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis
- Relatório de Impacto à Proteção de Dados Pessoais — ANPD:
  https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/relatorio-de-impacto-a-protecao-de-dados-pessoais-ripd
- Regulamentações da ANPD:
  https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd
