# Validação da Sprint 25 — Etapa 2

## Testes direcionados

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q atlas/tests/test_resource_manager.py atlas/tests/test_resource_manager_integration.py
```

## Regressão completa

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Qualidade e compilação

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q atlas main.py gui_main.py api_main.py resource_manager_pilot.py
```

## Piloto local

```powershell
.\.venv\Scripts\python.exe resource_manager_pilot.py
```

O final esperado é:

```text
Licenças após liberação: 0
Nenhum processo ou configuração do computador foi alterado.
```

## Cobertura esperada

- métricas obrigatórias, opcionais e valores inválidos;
- estados normal, alerta e crítico nos limites exatos;
- orçamento de memória do perfil;
- admissão e liberação idempotente;
- liberação após exceção;
- capacidade por perfil;
- concorrência real na aquisição;
- preservação de operações leves sob pressão crítica;
- bloqueio de carga pesada sob alerta;
- proteção de hardware abaixo do mínimo;
- auditoria limitada e sem payload;
- integração do mesmo manager no Kernel e WorkflowEngine;
- falha estruturada sem chamar o Executor;
- compatibilidade com WorkflowEngine sem manager.

## Resultado desta entrega

```text
Testes direcionados:  44 passed
Regressão completa:   1331 passed, 2 warnings externos
Ruff global:          All checks passed
Compileall:           aprovado
Piloto local:         aprovado, licença devolvida e sem modificações
```

Os dois avisos são emitidos por `SpeechRecognition` ao importar os módulos
`aifc` e `audioop`, depreciados no Python 3.12. Nenhum aviso foi produzido pelo
Resource Manager.
