# Atlas — Sprint 28.10

## Copilot Bridge / API local do Atlas

Esta etapa cria uma API local no Atlas para receber mensagens vindas do widget visual do Business Lab.

Endpoint principal:

```text
POST http://127.0.0.1:8765/api/copilot/message
```

Health check:

```text
GET http://127.0.0.1:8765/health
```

## Segurança

- O servidor nasce em `127.0.0.1` por padrão.
- CORS fica limitado ao Business Lab local: `http://127.0.0.1:5055`.
- É possível exigir token local usando a variável:

```powershell
$env:ATLAS_COPILOT_TOKEN="um-token-local"
```

Quando essa variável estiver configurada, o widget precisa mandar o header:

```text
X-Atlas-Copilot-Token: um-token-local
```

## Rodar

```powershell
cd C:\Atlas_OFICIAL

$env:ATLAS_BUSINESS_LAB_URL="http://127.0.0.1:5055"
$env:ATLAS_BUSINESS_LAB_EMAIL="consultor@nexyra.lab"
$env:ATLAS_BUSINESS_LAB_PASSWORD="Consultor123!"

.\.venv\Scripts\python.exe tools\run_atlas_copilot_bridge.py
```

## Teste manual

Com o Business Lab e o Copilot Bridge abertos:

```powershell
$body = @{
  message = "Resuma esse lead"
  context = @{
    page = "lead_detail"
    lead_code = "SIM-00001"
    route = "/leads/1"
    user_email = "consultor@nexyra.lab"
  }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8765/api/copilot/message" `
  -ContentType "application/json" `
  -Body $body | ConvertTo-Json -Depth 8
```

## Comandos suportados nesta etapa

- `Resuma esse lead`
- `Qual a próxima ação desse lead?`
- `Registre atendimento dizendo que pediu retorno amanhã`
- `Crie um retorno amanhã às 15h`
- `Mostre os cursos`
- `Resumo do dashboard`

## Observação

Esta etapa ainda não altera o JavaScript do widget. Ela prepara o Atlas para receber as mensagens. A próxima etapa conecta o widget HTML do Business Lab a este endpoint local.
