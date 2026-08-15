# Sprint 20 — Etapa 3: execução de comandos pela API

Esta etapa conecta a API HTTP ao núcleo operacional do Atlas sem duplicar o
fluxo de planejamento e execução.

## Endpoint

`POST /api/v1/commands`

Requer a chave administrativa no cabeçalho `X-API-Key` e o escopo
`commands:execute`.

Corpo da requisição:

```json
{
  "command": "Atlas, liste minhas memórias"
}
```

A resposta informa o identificador da requisição, mensagem, origem, sucesso,
quantidade de ações, cancelamento, encerramento e duração observada pela API.

## Runtime operacional

- inicialização preguiçosa no primeiro comando;
- reutilização do `AtlasGuiService` e do fluxo real do Controller;
- uma thread persistente para preservar a sessão do Playwright;
- apenas um comando ativo por vez;
- encerramento limpo no ciclo de vida do FastAPI;
- timeout HTTP configurável por `ATLAS_API_COMMAND_TIMEOUT`.

O timeout limita apenas a espera da requisição. Se ele for atingido, o comando
continua no núcleo e novas chamadas recebem conflito até a execução terminar.

## Códigos relevantes

| Código | Significado |
| --- | --- |
| `200` | comando concluído |
| `401` | chave ausente ou inválida |
| `403` | chave válida sem permissão de execução |
| `409` | outro comando ainda está em execução |
| `422` | corpo ou comando inválido |
| `503` | runtime encerrado ou autenticação não configurada |
| `504` | a espera HTTP terminou; o núcleo ainda pode estar executando |

## Teste manual

1. Feche a interface gráfica para evitar dois núcleos operacionais.
2. Inicie `api_main.py`.
3. Abra `http://127.0.0.1:8765/docs`.
4. Autorize com a chave administrativa.
5. Execute `POST /api/v1/commands` com o JSON de exemplo.

Não publique capturas que mostrem o comando `curl` gerado pelo Swagger, pois
ele contém o valor completo da chave no cabeçalho.
