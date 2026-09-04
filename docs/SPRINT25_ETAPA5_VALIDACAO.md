# Validação da Sprint 25 — Etapa 5

## Testes direcionados

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q atlas/tests/test_admin_console_service.py atlas/tests/test_admin_console_integration.py atlas/tests/test_model_router.py atlas/tests/test_model_router_integration.py atlas/tests/test_lazy_components.py atlas/tests/test_lazy_integration.py
```

## Regressão completa

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q atlas main.py gui_main.py api_main.py admin_console_pilot.py
```

## Piloto

```powershell
.\.venv\Scripts\python.exe admin_console_pilot.py
```

O piloto deve terminar com Brain e Vision descarregados e nenhuma ação
executada.

## Cobertura

- saúde normal, atenção, crítica e indisponível;
- falhas isoladas de perfil, recursos, auditoria e lazy loading;
- imutabilidade e cópia segura do snapshot;
- ausência de mensagens internas e identificadores de auditoria;
- Brain descarregado após consulta;
- última decisão de modelo somente após uso;
- integração com o mesmo Kernel da GUI;
- ausência de controles mutáveis, threads de widgets e endpoint público.

## Resultado desta entrega

```text
Testes novos:         34 aprovados
Testes direcionados:  95 aprovados
Regressão completa:   1.426 aprovados, 2 avisos externos
Ruff global:          aprovado
Compileall:           aprovado
Piloto somente leitura: aprovado
```

Os dois avisos são de depreciação em dependências do `SpeechRecognition`
(`aifc` e `audioop`). O executor Linux usado na validação não possui a
biblioteca gráfica `libEGL.so.1`, portanto a abertura visual foi validada por
estrutura e compilação; o piloto funcional do serviço administrativo passou.
