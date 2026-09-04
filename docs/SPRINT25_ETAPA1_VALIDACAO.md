# Validação da Sprint 25 — Etapa 1

## Testes direcionados

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q atlas/tests/test_runtime_profile.py atlas/tests/test_runtime_profile_integration.py
```

## Regressão completa

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Qualidade e compilação

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q atlas main.py gui_main.py api_main.py runtime_profile_pilot.py
```

## Piloto local

```powershell
.\.venv\Scripts\python.exe runtime_profile_pilot.py
```

Para simular uma solicitação explícita sem alterar o `.env`:

```powershell
.\.venv\Scripts\python.exe runtime_profile_pilot.py --profile full
```

O final esperado é:

```text
Nenhum processo, arquivo ou configuração foi alterado.
```

## Cobertura esperada

- limites exatos para seleção Lite, Standard e Full;
- suporte, limitação temporária e equipamento abaixo do mínimo;
- perfil automático e solicitação explícita;
- redução transparente de perfil incompatível;
- orçamentos limitados por perfil;
- validação de RAM, CPU, disco, VRAM e horário;
- falha segura da métrica essencial;
- tolerância à indisponibilidade de métricas opcionais;
- sumário sem caminho, identidade, processo ou serial;
- integração do perfil antes dos componentes pesados;
- ausência de alteração de ambiente ou execução de subprocesso.

## Resultado desta entrega

```text
Testes direcionados:  49 passed
Regressão completa:   1287 passed, 2 warnings externos
Ruff global:          All checks passed
Compileall:           aprovado
Piloto local:         aprovado, sem modificações
```

Os dois avisos são emitidos por `SpeechRecognition` ao importar os módulos
`aifc` e `audioop`, depreciados no Python 3.12. Nenhum aviso foi produzido pelo
seletor de perfis ou pelo diagnóstico de recursos.
