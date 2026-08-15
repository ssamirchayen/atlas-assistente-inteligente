# Sprint 20 — segurança e auditoria da API local

Esta etapa conclui a Sprint 20 com uma trilha persistente de auditoria e
controles defensivos para a API local do Atlas.

## Endpoint de auditoria

`GET /api/v1/audit/events`

O endpoint exige a chave administrativa e o escopo `audit:read`. Os eventos
são devolvidos do mais recente ao mais antigo e aceitam estes filtros:

| Parâmetro | Regra |
| --- | --- |
| `limit` | entre 1 e 200; padrão 50 |
| `event_type` | tipo exato, como `command.completed` |
| `workflow_id` | identificador exato da execução |

## Eventos registrados

- autenticação aceita, recusada ou indisponível;
- recebimento, conclusão, rejeição, falha e timeout de comandos;
- consulta de workflow inexistente;
- solicitação ou rejeição de cancelamento.

Cada evento contém identificador, horário UTC, principal, workflow, resultado,
código HTTP, duração quando aplicável e metadados sanitizados.

## Proteção de conteúdo sensível

A auditoria não armazena:

- valor de `X-API-Key`;
- comando completo enviado pelo usuário;
- resposta textual do Atlas;
- motivo completo de cancelamento;
- exceções internas ou credenciais.

Comandos e motivos recebem uma impressão SHA-256 e o tamanho do texto. Isso
permite correlacionar ocorrências idênticas sem reconstruir o conteúdo.

## Persistência e retenção

O banco local fica em `data/api_audit.db`, caminho já ignorado pelo Git. A
retenção padrão mantém até 10.000 eventos e até 90 dias. Os limites podem ser
ajustados no `.env`:

```text
ATLAS_API_AUDIT_RETENTION_DAYS=90
ATLAS_API_AUDIT_MAX_EVENTS=10000
```

A API não expõe operação para alterar ou apagar eventos. A limpeza ocorre
somente pela política automática de retenção.

## Controles HTTP

- servidor vinculado a `127.0.0.1`;
- lista de hosts permitidos: `127.0.0.1`, `localhost` e host de testes;
- `Cache-Control: no-store` nas respostas `/api/v1`;
- `X-Content-Type-Options: nosniff`;
- `X-Frame-Options: DENY`;
- `Referrer-Policy: no-referrer`;
- autorização do Swagger não persiste após recarregar a página.

## Teste manual

1. Inicie `api_main.py` e abra `http://127.0.0.1:8765/docs`.
2. Autorize com `ATLAS_API_KEY`.
3. Execute um comando em `POST /api/v1/commands`.
4. Abra `GET /api/v1/audit/events` e execute com `limit=20`.
5. Confirme que aparecem eventos `command.received` e
   `command.completed`, sem o texto completo do comando.

O Swagger mostra a chave no exemplo `curl` enquanto a autorização estiver
ativa. Não publique capturas dessa área. Se a chave for exposta, gere outra,
substitua `ATLAS_API_KEY` no `.env` e reinicie a API.
