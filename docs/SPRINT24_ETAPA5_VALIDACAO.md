# Validação da Sprint 24 — Etapa 5

## Testes direcionados

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q atlas/tests/test_privacy_incidents.py atlas/tests/test_privacy_impact.py atlas/tests/test_privacy_catalog.py
```

## Regressão completa

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Qualidade e compilação

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q atlas main.py gui_main.py api_main.py privacy_governance_pilot.py
```

## Piloto seguro

```powershell
.\.venv\Scripts\python.exe privacy_governance_pilot.py
```

O final esperado é:

```text
Nenhuma comunicação foi enviada e nenhum dado real foi acessado.
```

## Cobertura de segurança esperada

- validação de identificadores, enums, horários e isolamento por organização;
- registro sem payload de dados pessoais;
- conclusão relevante, não relevante e indeterminada;
- revisão humana obrigatória para toda triagem;
- prazos de três e vinte dias úteis;
- plano preliminar e validação de fatos mínimos;
- duas aprovações distintas para comunicação;
- tarefas manuais, sem envio de rede;
- registro idempotente de digests de evidência;
- RIPD vinculado ao inventário e falha para fluxo inexistente;
- matriz de risco inerente e residual;
- detecção de dados sensíveis, crianças e transferência internacional;
- bloqueio de seções incompletas e risco residual alto ou crítico;
- duas aprovações distintas para o RIPD;
- relatório com digests e sem declaração automática de conformidade;
- auditoria pseudonimizada e coleções limitadas.

## Verificação do pacote incremental

O ZIP deve conter apenas os 11 arquivos novos ou alterados nesta etapa, sem
`.env`, `.venv`, bancos, logs, caches ou bytecode. Para confirmar em PowerShell:

```powershell
tar -tf .\atlas_sprint24_etapa5_incidentes_ripd_incremental.zip
```

## Resultado desta entrega

```text
Testes direcionados:  64 passed
Regressão completa:   1238 passed, 2 warnings externos
Ruff global:          All checks passed
Compileall:           aprovado
Piloto supervisionado: aprovado, sem rede ou dados reais
```

Os dois avisos são emitidos por `SpeechRecognition` ao importar os módulos
`aifc` e `audioop`, depreciados no Python 3.12. Nenhum aviso foi produzido pelos
componentes de incidentes ou RIPD.
