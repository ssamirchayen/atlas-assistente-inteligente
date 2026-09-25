# Atlas — Sprint 28.14
## Atendimentos e mensagens em lote

Esta etapa adiciona ao Atlas a capacidade de preparar e registrar atendimentos/mensagens para vários leads do Nexyra Business Lab.

## Objetivo

Transformar o Atlas em um copiloto operacional capaz de trabalhar em escala dentro do Business Lab, sem depender de abrir lead por lead.

Exemplo de comando:

```text
Atlas, prepare mensagens para 10 leads novos de Radiologia e crie retornos para amanhã às 15h.
```

## Segurança

Nesta etapa, o Atlas **não envia WhatsApp real** e **não envia e-mail real**.

Ele trabalha assim:

1. Busca leads pela API do Business Lab.
2. Filtra por curso, status, prioridade e quantidade.
3. Gera mensagens personalizadas.
4. Mostra uma prévia segura.
5. Só registra atendimentos/retornos no Business Lab se receber `confirmed=true`.

## Arquivos adicionados/alterados

```text
atlas/copilot/business_lab.py
atlas/copilot/batch_messages.py
tools/run_business_lab_batch_messages.py
tests/test_atlas_copilot_batch_messages.py
README_ATLAS_BATCH_MESSAGES.md
```

## Teste unitário

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q tests\test_atlas_copilot_batch_messages.py
```

## Prévia segura com Business Lab aberto

```powershell
cd C:\Atlas_OFICIAL

$env:ATLAS_BUSINESS_LAB_URL="http://127.0.0.1:5055"
$env:ATLAS_BUSINESS_LAB_EMAIL="consultor@nexyra.lab"
$env:ATLAS_BUSINESS_LAB_PASSWORD="Consultor123!"

.\.venv\Scripts\python.exe tools\run_business_lab_batch_messages.py
```

## Registrar no Business Lab

Use apenas quando a prévia estiver correta:

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_batch_messages.py --confirm
```

## Observação comercial

Esta etapa mostra o Atlas poupando tempo de verdade, porque substitui tarefas repetitivas de leitura, priorização, escrita de mensagens, registro de atendimentos e criação de retornos por um fluxo único em lote.
