# Sprint 24 — Etapa 2: PrivacyPolicyEngine

## Objetivo

A Etapa 2 cria uma barreira comum entre os componentes do Atlas e qualquer
tratamento de dados pessoais. O motor recebe uma política previamente definida
e aprovada pela organização e decide se uma solicitação técnica pode continuar.

Ele não determina qual hipótese legal é adequada para uma empresa. Essa decisão
continua sendo do controlador, com sua documentação e orientação jurídica.

## Fluxo de decisão

Uma solicitação só é permitida quando todos os requisitos abaixo coincidem:

1. organização do operador e da solicitação;
2. tratamento existente no inventário da Etapa 1;
3. política exata para tratamento e finalidade;
4. política ativa e com evidência de aprovação;
5. ação, papel e escopos autorizados;
6. base legal previamente declarada na política;
7. categorias e campos inventariados e necessários;
8. permissões adicionais para dados sensíveis, crianças ou transferência;
9. recibo válido quando a base declarada depende de consentimento.

Qualquer ausência ou divergência resulta em bloqueio. Não existe política ampla
ou fallback que autorize uma finalidade parecida.

## Consentimento

O registro em memória da etapa representa consentimentos por recibos com:

- organização, tratamento, finalidade e categorias exatas;
- titular pseudonimizado com HMAC-SHA256;
- evidência convertida em hash, sem guardar seu conteúdo;
- responsável pela concessão representado somente por hash;
- horário com fuso, expiração opcional e revogação idempotente;
- isolamento entre organizações e titulares.

O recibo só é exigido quando o controlador declara `personal.consent` ou
`sensitive.specific_consent`. Outras hipóteses declaradas não são convertidas
indevidamente em consentimento.

Nesta etapa, políticas, recibos e auditoria são estruturas em memória. A futura
persistência deve receber controle de acesso, retenção, direitos do titular e
proteção em repouso antes de ser ativada em produção.

## Minimização e pseudonimização

Após uma decisão permitida, o `DataMinimizer`:

- remove campos que não foram solicitados e autorizados;
- mascara os campos definidos pela política;
- pseudonimiza campos definidos usando HMAC-SHA256 e namespace por organização,
  tratamento, finalidade e nome do campo;
- devolve um resultado imutável cujo `repr` não expõe os valores tratados.

A chave HMAC deve ter pelo menos 32 bytes e, em produção, precisa vir de um
cofre de segredos, com acesso mínimo e rotação planejada. Não se deve reutilizar
a chave fictícia do piloto.

## Auditoria segura

A trilha padrão permanece somente em memória e guarda no máximo 1.000 eventos.
Ela contém decisão, organização, identificador do operador em hash, tratamento,
finalidade, ação, categorias, quantidade de campos, resultado e motivo.

Ela não recebe:

- payload;
- texto de conversa;
- áudio ou imagem;
- identificador bruto de operador ou titular;
- recibo de consentimento bruto;
- token, senha ou chave.

O novo fluxo `privacy.policy_decision_audit` foi adicionado ao inventário, que
passa de 14 para 15 atividades técnicas mapeadas.

## Limites jurídicos e operacionais

Esta implementação apoia os princípios de finalidade, adequação, necessidade,
segurança, prevenção, não discriminação e responsabilização. Ela não substitui
aviso de privacidade, registro jurídico, avaliação de legítimo interesse, RIPD,
contratos com operadores ou atendimento de direitos.

Referências oficiais consultadas:

- [Lei Geral de Proteção de Dados — texto compilado](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm)
- [Perguntas frequentes da ANPD](https://www.gov.br/anpd/pt-br/acesso-a-informacao/perguntas-frequentes)
- [Guia de agentes de tratamento e encarregado](https://www.gov.br/anpd/pt-br/documentos-e-publicacoes/guia-agentes-de-tratamento-e-encarregado.pdf)
- [Guia de segurança para agentes de pequeno porte](https://www.gov.br/anpd/pt-br/documentos-e-publicacoes/guia-vf.pdf)

## Próxima etapa

A Etapa 3 implementará solicitações de titulares com identificação segura,
consulta, correção, portabilidade técnica e exclusão supervisionada, reutilizando
as decisões e a auditoria desta etapa.
