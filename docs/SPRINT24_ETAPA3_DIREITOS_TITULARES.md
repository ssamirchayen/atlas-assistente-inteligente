# Sprint 24 — Etapa 3: Direitos dos Titulares

## Objetivo

A Etapa 3 cria o fluxo técnico para receber, verificar, revisar e executar
solicitações de confirmação, acesso, correção, portabilidade e exclusão. Ela
reutiliza o inventário e o `PrivacyPolicyEngine`: nenhuma fonte pode ser lida ou
alterada sem uma política ativa para a finalidade `fulfill.subject_rights`.

O Atlas não se apresenta como canal oficial de uma organização sem que ela
configure o controlador, o encarregado, os procedimentos e os canais seguros.

## Fluxo protegido

1. O titular ou representante apresenta requerimento expresso.
2. O Atlas pseudonimiza o identificador e guarda apenas fontes e campos pedidos.
3. Um código aleatório é emitido para entrega por canal externo verificado.
4. O código expira em 10 minutos e bloqueia após cinco erros.
5. Um encarregado ou operador com papel e escopo próprios revisa o pedido.
6. Leitura exige uma aprovação; correção e exclusão exigem duas pessoas distintas.
7. A execução exige uma segunda confirmação textual exata.
8. Cada fonte passa pelo `PrivacyPolicyEngine` antes de qualquer acesso.
9. A resposta de acesso é minimizada e existe somente no resultado da chamada.
10. A auditoria recebe apenas metadados pseudonimizados.

## Direitos implementados

| Direito | Ação técnica | Comportamento padrão |
| --- | --- | --- |
| Confirmação | verifica existência por fonte | conclui após identidade e aprovação |
| Acesso | entrega somente campos autorizados | conclui sem persistir a resposta |
| Portabilidade | usa permissão específica de exportação | devolve estrutura em memória |
| Correção | valida campos e monta plano | `dry-run`, sem alterar a fonte |
| Exclusão | consulta impedimentos e monta plano | `dry-run`, sem excluir registros |

Mutações reais existem apenas para adaptadores explicitamente habilitados pelo
integrador. Elas continuam exigindo política ativa, duas aprovações distintas e
confirmação final. Uma mutação real envolvendo mais de uma fonte é bloqueada
nesta etapa porque ainda não existe transação ou rollback distribuído.

## Prazos e respostas

O modelo registra a resposta simplificada de confirmação ou acesso como
imediata. Quando o titular solicita declaração completa desses dois direitos, o
prazo técnico é registrado em 15 dias. Para os demais pedidos, o Atlas não
inventa um prazo geral: a organização deve considerar a legislação, eventual
regulamentação e regras setoriais aplicáveis.

Uma resposta completa ainda precisa ser complementada pela organização com
origem, critérios, finalidade, identificação e contato do controlador, uso
compartilhado, responsabilidades e outras informações aplicáveis. A Etapa 3
fornece o pacote técnico dos dados, não uma decisão jurídica automática.

## Exclusão e conservação

Cada adaptador retorna um `DeletionPlan` com contagem e códigos estruturados de
retenção. Qualquer impedimento bloqueia a exclusão. Isso permite documentar, por
exemplo, uma obrigação de conservação sem gravar uma justificativa livre que
possa conter mais dados pessoais.

A política comum de retenção, propagação da eliminação para operadores, descarte
verificável e evidências persistentes será implementada na Etapa 4.

## Segurança e privacidade

- o identificador bruto do titular só existe durante a pseudonimização;
- códigos de identidade não aparecem em `repr` ou auditoria;
- valores de correção são parâmetros efêmeros e não entram no pedido;
- respostas de acesso não são guardadas para repetição;
- auditoria tem limite configurável, padrão de 1.000 eventos;
- solicitações têm limite configurável, padrão de 1.000;
- solicitações ativas nunca são removidas para abrir espaço;
- nenhuma API, banco, arquivo ou canal externo é ativado automaticamente.

## Referências oficiais

- [LGPD compilada — artigos 18 a 20](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm)
- [Perguntas frequentes da ANPD — prazos e direitos](https://www.gov.br/anpd/pt-br/acesso-a-informacao/perguntas-frequentes)
- [Direitos dos titulares — ANPD](https://www.gov.br/anpd/pt-br/assuntos/titular-de-dados-1/direito-dos-titulares)

## Limites da etapa

- não confirma identidade por e-mail, WhatsApp ou biometria;
- não publica uma API externa;
- não gera arquivo contendo dados pessoais;
- não conecta automaticamente bancos reais;
- não decide se um pedido deve ser atendido juridicamente;
- não executa comunicação automática a operadores ou terceiros;
- não substitui o encarregado ou a avaliação jurídica da organização.
