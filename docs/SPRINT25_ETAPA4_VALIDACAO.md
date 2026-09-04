# Validação da Sprint 25 — Etapa 4

## Testes direcionados

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q atlas/tests/test_model_router.py atlas/tests/test_model_router_integration.py atlas/tests/test_lazy_components.py atlas/tests/test_lazy_integration.py
```

## Regressão e qualidade

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q atlas main.py gui_main.py api_main.py model_router_pilot.py
```

## Piloto seguro

```powershell
.\.venv\Scripts\python.exe model_router_pilot.py
```

O piloto utiliza inventário, hardware e pressão simulados. Ele não abre o
Ollama, não carrega modelos e não acessa a rede.

## Cobertura

- seleção por perfil e tarefa;
- redução por pressão warning e critical;
- limites de RAM, RAM disponível, VRAM e contexto;
- inventário local, cache e alias `:latest`;
- fallback quando inventário ou modelo estão indisponíveis;
- validação de nomes e tarefas;
- decisão observável sem conteúdo do usuário;
- payload roteado e compatibilidade do Brain antigo;
- criação do roteador dentro da factory lazy.

## Resultado desta entrega

```text
Testes novos:         35 aprovados
Testes direcionados:  64 aprovados
Regressão completa:   1.392 aprovados, 2 avisos externos
Ruff global:          aprovado
Compileall:           aprovado
Piloto seguro:        aprovado
```

Os dois avisos são de depreciação em dependências do `SpeechRecognition`
(`aifc` e `audioop`) e não foram introduzidos pelo Model Router.
