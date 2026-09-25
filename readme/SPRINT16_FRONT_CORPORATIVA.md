# Sprint 16 — Interface corporativa

Nova identidade visual do Atlas com foco principal na conversa.

## O que mudou

- Layout corporativo em azul-marinho, branco e azul institucional.
- Conversa ampliada e posicionada como área principal.
- Painel lateral compacto com workflow, modo, CPU e memória.
- Mensagens visualmente separadas entre usuário, Atlas e sistema.
- Campo de comando e botões redesenhados.
- Estados de execução, voz, cancelamento e erro preservados.
- Novo ícone institucional do Atlas.

## Aplicação

1. Feche o Atlas.
2. Extraia o ZIP na raiz de `C:\Atlas_OFICIAL`.
3. Confirme a substituição dos arquivos.
4. Execute:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

```powershell
.\.venv\Scripts\python.exe -m ruff check atlas gui_main.py
```

5. Inicie a interface:

```powershell
.\.venv\Scripts\python.exe gui_main.py
```

Esta atualização altera somente a apresentação da interface. O backend,
o workflow, a voz e a automação do navegador permanecem integrados.
