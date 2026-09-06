# Hotfix — execução direta dos scripts de integração

Ao executar:

`python tools\test_integration_framework.py`

o Python coloca `tools` no início do `sys.path`, não necessariamente a raiz
`C:\Atlas_OFICIAL`. Por isso o pacote `atlas` não era encontrado.

Este hotfix:
- identifica automaticamente a raiz do projeto;
- adiciona a raiz ao `sys.path`;
- usa `importlib` para evitar E402 no Ruff;
- corrige os dois utilitários de integração.
