# Atlas — Sprint 28.17

## Validação final da operação em escala

Esta etapa fecha a Sprint 28 validando o fluxo completo:

- Business Lab online.
- Atlas Copilot Bridge online.
- Resumo da tela atual.
- Resumo de lead aberto.
- Triagem em lote.
- Mensagens/atendimentos em lote com prévia.
- Execução em lote somente com confirmação explícita.
- Relatórios inteligentes com downloads.
- Próxima ação operacional.
- Trava de segurança quando o usuário pede ação de lead sem lead aberto.

Por padrão, o script roda em modo seguro de prévia. Para executar lote real no Business Lab, use `--confirm-batch`.

## Rodar

```powershell
cd C:\Atlas_OFICIAL

$env:ATLAS_BUSINESS_LAB_URL="http://127.0.0.1:5055"
$env:ATLAS_BUSINESS_LAB_EMAIL="consultor@nexyra.lab"
$env:ATLAS_BUSINESS_LAB_PASSWORD="Consultor123!"

.\.venv\Scripts\python.exe tools\run_business_lab_operation_scale_validation.py
```

## Rodar com execução real em lote

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_operation_scale_validation.py --confirm-batch
```

## Saída

Os relatórios são salvos em:

```text
data\business_lab_benchmark
```

Arquivos gerados:

- `atlas_operation_scale_validation_*.json`
- `atlas_operation_scale_validation_*.md`

## Segurança

Este validador não envia WhatsApp/e-mail real. A execução real com `--confirm-batch` registra histórico/retornos/status no Business Lab sintético.
