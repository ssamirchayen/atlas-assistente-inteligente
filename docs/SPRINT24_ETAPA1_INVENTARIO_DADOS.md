# Sprint 24 — Etapa 1: Inventário e classificação de dados

## Resultado

O Atlas passa a possuir um inventário técnico central de operações de
tratamento. Ele registra metadados sobre os fluxos; nunca varre bancos, lê
conversas, abre capturas, consulta telefones ou exporta credenciais.

O catálogo inicial contém 14 operações:

| Área | Tratamento inventariado |
| --- | --- |
| Core | contexto recente da conversa |
| Memória | fatos persistentes e embeddings locais |
| Sessões | timeline e continuidade operacional |
| API | auditoria autenticada e redigida |
| Voz | reconhecimento externo, TTS e cache local |
| Vision | captura transitória e análise local |
| Internet | consultas enviadas aos provedores configurados |
| Escola | CRM, opt-in, leads e WhatsApp oficial |
| Atlas Edge | dispositivo, funcionário, fila, onboarding e auditoria |
| Agendador | tarefas persistentes em JSON |
| Auditoria | metadados de conectores e automação visual |
| Logs | diagnóstico local da aplicação |
| Segredos | localização técnica das credenciais, sem valores |

## Classificação

Cada registro informa:

- natureza técnica do dado;
- categorias e tipos de titular;
- coleta, acesso, uso, armazenamento, transmissão e eliminação;
- finalidade preliminar e origem;
- destinatários e armazenamentos;
- retenção realmente existente no código;
- processamento local ou serviço remoto;
- transferência internacional a avaliar;
- decisão automatizada;
- controles implementados e lacunas;
- risco técnico preliminar.

`requires_controller_definition` é intencional. O Atlas não escolhe sozinho a
base legal de uma empresa. O controlador deverá registrar a decisão e sua
referência em uma etapa posterior.

## Falha segura e ausência de falsa conformidade

O inventário não marca SQLite, JSON, logs ou `.env` como criptografados porque
essa proteção ainda não existe de forma comum no projeto. Também diferencia
retenção por prazo, limite de quantidade, descarte transitório, política externa
e retenção ainda indefinida.

Operações com crianças/adolescentes, dados sensíveis, transmissão externa ou
decisão automatizada recebem risco elevado. Isso é um alerta técnico, não um
parecer jurídico nem um diagnóstico de impacto.

## Uso seguro

Resumo sem gravar arquivo:

```powershell
.\.venv\Scripts\python.exe privacy_inventory_pilot.py
```

Exportação explícita dos metadados:

```powershell
.\.venv\Scripts\python.exe privacy_inventory_pilot.py `
  --json data/privacy/inventory.json
```

O modo estrito retorna código 2 enquanto existirem pendências altas ou críticas:

```powershell
.\.venv\Scripts\python.exe privacy_inventory_pilot.py --strict
```

Esse retorno é esperado nesta primeira etapa e poderá ser usado como quality
gate após a implementação das políticas das Etapas 2 a 5.

## Limites

O inventário é a base técnica para adequação. Conformidade real depende das
operações da organização, avisos de privacidade, contratos, decisões do
controlador, operadores, encarregado e revisão jurídica.

Referências oficiais:

- [LGPD compilada](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/L13709compilado.htm)
- [Perguntas frequentes da ANPD](https://www.gov.br/anpd/pt-br/acesso-a-informacao/perguntas-frequentes)
- [Guia de agentes de tratamento e encarregado](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia-orientativo-para-definicoes-dos-agentes-de-tratamento-de-dados-pessoais-e-do-encarregado)
- [Guia de segurança da informação](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia-orientativo-sobre-seguranca-da-informacao-para-agentes-de-tratamento-de-pequeno-porte)
