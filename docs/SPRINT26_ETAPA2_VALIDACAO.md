# Validação — Sprint 26 / Etapa 2

Execute na raiz `C:\Atlas_OFICIAL`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Depois:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

E inicie a GUI:

```powershell
.\.venv\Scripts\python.exe gui_main.py
```

## Checklist visual
- Workspace abre em dark mode.
- Sidebar exibe ATLAS / by NEXYRA.
- Header exibe Workspace, Atlas Core e Runtime Local.
- Conversa permanece como maior área da interface.
- Painel direito exibe System Pulse, Recursos, Ações rápidas e Ambiente.
- Campo de comando, Microfone, Escuta contínua, Enviar e Cancelar funcionam.

## Checklist funcional
- Envio por Enter e botão Enviar.
- Microfone manual.
- Escuta contínua.
- `Atlas, pare` interrompe fala/workflow.
- Histórico operacional abre no chat.
- Admin Console abre normalmente.
- Retomada continua disponível quando existir pendência.
- Somente uma instância do Atlas permanece aberta.
