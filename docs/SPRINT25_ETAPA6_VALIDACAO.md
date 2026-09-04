# Validação da Sprint 25 — Etapa 6

## Testes direcionados

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q atlas/tests/test_runtime_paths.py atlas/tests/test_release_validator.py atlas/tests/test_windows_installer_structure.py atlas/tests/test_browser_session_recovery.py
```

## Regressão

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q atlas main.py gui_main.py api_main.py installer_validation_pilot.py tools\validate_release.py
```

## Piloto seguro

```powershell
.\.venv\Scripts\python.exe installer_validation_pilot.py
```

O piloto cria uma pasta temporária simulada, valida e a remove automaticamente.
Ele não instala programas e não altera dados do Atlas.

## Cobertura

- caminhos em modo fonte e congelado;
- `%LOCALAPPDATA%` e diretório configurável;
- manifesto válido, inválido e incompleto;
- ausência de arquivo obrigatório;
- bloqueio de `.env`, bancos, logs, chaves, caches e symlinks;
- limite de tamanho e ordenação determinística;
- PyInstaller `onedir` e entrada GUI;
- testes antes do build e validação antes do Inno Setup;
- instalação sem administrador e desinstalação preservando dados;
- Edge do sistema no executável e ausência de download de modelos.

## Resultado desta entrega

```text
Testes novos:          48 aprovados
Testes direcionados:   52 aprovados
Regressão completa:    1.474 aprovados, 2 avisos externos
Ruff global:           aprovado
Compileall:            aprovado
Piloto do manifesto:   aprovado
```

Os dois avisos são de depreciação em dependências do `SpeechRecognition`
(`aifc` e `audioop`). A compilação final do `.EXE` exige Windows, PyInstaller e
Inno Setup 6; por isso, neste executor Linux foram validados o pipeline, os
scripts, o manifesto e a distribuição simulada, não um binário Windows.
