# Guia de desenvolvimento

## Ambiente

Use Python 3.13 dentro da `.venv`:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Ciclo de validação

Antes de concluir uma alteração:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Para verificar sintaxe de todo o backend:

```powershell
.\.venv\Scripts\python.exe -m compileall -q atlas main.py gui_main.py
```

## Regras de arquitetura

- `AtlasKernel` apenas instancia e conecta componentes.
- `AtlasController` é o ponto central de orquestração.
- `Planner` cria ações; ele não executa automações.
- `WorkflowEngine` controla o ciclo das etapas.
- `TaskManager` controla estado; ele não executa tarefas.
- `Executor` retorna sempre `ExecutionResult`.
- Automação concreta pertence a `atlas/automation/`.
- Estado local não deve ser incluído em commits ou ZIPs de entrega.

## Como adicionar uma automação

1. Implemente o comportamento no módulo adequado em `atlas/automation/`.
2. Registre um handler no dicionário do `AutomationEngine`.
3. Faça o Planner produzir uma `Action` com tipo e parâmetros compatíveis.
4. Adicione testes sem abrir aplicações reais.
5. Execute Pytest e Ruff.

## Como adicionar um fluxo

Use `WorkflowBuilder`, `WorkflowStep` e `WorkflowState`. Compartilhe dados pelo
`WorkflowContext` e respeite `state.throw_if_cancelled()` em operações longas.

## Empacotamento limpo

Não inclua:

- `.venv/`;
- `__pycache__/`;
- `.pytest_cache/` e `.ruff_cache/`;
- `.coverage` e `htmlcov/`;
- `.env`;
- bancos e sessões em `data/` e `atlas_data/`;
- logs e relatórios locais do Ruff.

O arquivo `.gitignore` contém a lista oficial dessas exclusões.
