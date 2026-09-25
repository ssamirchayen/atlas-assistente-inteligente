# Atlas — Sprint 28.15.1
## Atualização de status após execução em lote

Esta etapa melhora a execução em lote do Atlas no Nexyra Business Lab.

Antes, o Atlas registrava atendimentos e criava retornos, mas não alterava o status principal dos leads na lista.

Agora, após confirmação, o Atlas também pode atualizar o status dos leads processados.

## O que entrou

- Atualização automática para `follow_up` quando o lote cria retornos.
- Atualização automática para `em_atendimento` quando o lote registra atendimento em leads novos.
- Atualização explícita quando o comando pede um status específico.
- Prévia segura mostrando quantos leads terão status alterado.
- Proteção contra mudanças automáticas em leads `convertido` ou `perdido`, salvo comando explícito.
- Contadores separados de atendimentos, retornos, status atualizados, status ignorados e falhas.

## Exemplos no painel Atlas

```text
Atlas, prepare mensagens para 5 leads novos de Radiologia, crie retornos para amanhã às 15h e atualize status para follow_up.
```

```text
Atlas, registre atendimentos para 10 leads novos e atualize status para em_atendimento.
```

```text
Atlas, faça triagem dos leads novos de Radiologia, registre atendimento, crie retorno e mova os leads para follow_up.
```

## Fluxo seguro

1. O Atlas mostra a prévia.
2. O usuário confirma no painel.
3. O Atlas registra atendimentos.
4. O Atlas cria retornos, se solicitado.
5. O Atlas atualiza o status dos leads, quando aplicável.

Nenhum WhatsApp/e-mail real é enviado nesta etapa.

## Teste rápido pelo terminal

Com o Business Lab rodando:

```powershell
cd C:\Atlas_OFICIAL

$env:ATLAS_BUSINESS_LAB_URL="http://127.0.0.1:5055"
$env:ATLAS_BUSINESS_LAB_EMAIL="consultor@nexyra.lab"
$env:ATLAS_BUSINESS_LAB_PASSWORD="Consultor123!"

.\.venv\Scripts\python.exe tools\run_business_lab_batch_messages.py --confirm
```

A resposta deve incluir algo como:

```text
Status atualizados para follow_up: X/Y.
```

Depois abra os leads no Business Lab e confira a lista/histórico.
