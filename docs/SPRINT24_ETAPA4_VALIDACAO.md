# Validação da Sprint 24 — Etapa 4

## Testes direcionados

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q atlas/tests/test_privacy_retention.py atlas/tests/test_privacy_disposal.py atlas/tests/test_privacy_catalog.py
```

## Regressão completa

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Qualidade e compilação

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q atlas privacy_retention_pilot.py
```

## Piloto seguro

```powershell
.\.venv\Scripts\python.exe privacy_retention_pilot.py
```

O final esperado é:

```text
Registro fictício preservado: True
Nenhum dado foi excluído; o piloto usa dry-run por padrão.
```

## Cobertura de segurança esperada

- validação de regra, versão, prazo e carência;
- falha fechada para política ausente, inativa ou sem marco temporal;
- isolamento entre organizações;
- bloqueio global ou por titular pseudonimizado;
- expiração e liberação idempotente de bloqueios;
- duas aprovações humanas distintas;
- confirmação textual exata;
- plano com validade curta;
- revalidação contra novo bloqueio ou nova versão;
- `dry-run` sem mutação;
- exclusão lógica única, inclusive sob concorrência;
- comprovante e auditoria sem payload;
- tarefas pendentes para comunicação a operadores;
- ausência de execução automática para anonimização e bloqueio.

## Verificação do pacote incremental

O ZIP deve conter apenas os 11 arquivos novos ou alterados nesta etapa, sem
`.env`, `.venv`, bancos, logs, caches ou bytecode. Para confirmar em PowerShell:

```powershell
tar -tf .\atlas_sprint24_etapa4_retencao_descarte_incremental.zip
```

## Resultado desta entrega

```text
Testes direcionados: 67 passed
Regressão completa:   1184 passed, 2 warnings externos
Ruff global:          All checks passed
Compileall:           aprovado
Piloto dry-run:       aprovado, registro fictício preservado
```

Os dois avisos são emitidos por `SpeechRecognition` ao importar módulos de
áudio depreciados no Python 3.12. Nenhum aviso foi produzido pelos componentes
de retenção e descarte.
