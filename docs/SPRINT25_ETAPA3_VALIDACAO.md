# Validação da Sprint 25 — Etapa 3

## Testes direcionados

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q atlas/tests/test_lazy_components.py atlas/tests/test_lazy_integration.py atlas/tests/test_runtime_profile_integration.py
```

## Regressão completa

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Qualidade e compilação

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q atlas main.py gui_main.py api_main.py lazy_loading_pilot.py
```

## Piloto seguro

```powershell
.\.venv\Scripts\python.exe lazy_loading_pilot.py
```

O resultado deve mostrar Brain `ready`, Vision `unloaded` e terminar com:

```text
Nenhum modelo, captura ou configuração real foi acessado.
```

## Cobertura esperada

- ausência de execução da factory no registro;
- primeira carga e reutilização da instância;
- concorrência com construção única;
- espera das demais threads;
- falha armazenada sem mensagem sensível;
- recuperação explicitamente solicitada;
- proteção contra factory recursiva;
- factory que retorna `None`;
- proxy de atributo e objeto chamável;
- `repr` e teste booleano sem carga;
- nomes seguros e registro sem duplicidade;
- preload somente de nomes explícitos;
- Brain compartilhado com o Planner;
- imports pesados fora da inicialização do módulo;
- compatibilidade com perfil e Resource Manager existentes.

## Resultado desta entrega

```text
Testes direcionados: 29 aprovados
Regressão completa:   1.357 aprovados, 2 avisos externos
Ruff global:          aprovado
Compileall:           aprovado
Piloto seguro:        aprovado
```

Os dois avisos são de depreciação em dependências do `SpeechRecognition`
(`aifc` e `audioop`) e não foram introduzidos pelo lazy loading.
