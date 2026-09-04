# Sprint 25 — Etapa 6: instalador Windows

## Arquitetura de distribuição

O pipeline possui três barreiras sequenciais:

1. `pytest` e Ruff validam o código;
2. PyInstaller gera `dist/Atlas/Atlas.exe` em modo `onedir`;
3. o validador rejeita dados privados antes de o Inno Setup gerar o instalador.

O formato `onedir` foi escolhido para tornar inicialização, diagnóstico e
atualizações mais previsíveis do que um executável temporário `onefile`.

## Instalação

O Inno Setup instala em `%LOCALAPPDATA%\Programs\Atlas`, sem solicitar
privilégio administrativo. Ele cria um atalho no menu Iniciar e oferece um
atalho opcional na Área de Trabalho.

Os dados mutáveis ficam separados em `%LOCALAPPDATA%\Atlas`:

- `.env` do usuário;
- bancos e sessões em `data`;
- logs;
- cache de voz e capturas permitidas.

A desinstalação remove o aplicativo, mas preserva esse diretório para evitar
perda acidental de configurações e memórias.

## Navegador e Ollama

No executável congelado, o Playwright usa o Microsoft Edge já fornecido no
Windows 10/11. Assim, o instalador não precisa baixar uma cópia do Chromium.
O modo fonte continua usando a configuração atual.

Ollama e modelos locais não são incorporados: modelos podem conter vários
gigabytes e têm ciclos de versão e licenciamento próprios. Se o Ollama não
estiver disponível, o Atlas mantém sua mensagem de diagnóstico existente.

## Conteúdo privado bloqueado

O manifesto rejeita:

- `.env` real e chaves privadas;
- bancos SQLite;
- logs e sessões locais;
- caches Python e pastas de desenvolvimento;
- links simbólicos;
- arquivos obrigatórios ausentes;
- arquivos acima do limite definido.

## Build reproduzível

```powershell
cd C:\Atlas_OFICIAL
.\tools\build_windows_installer.ps1 -InstallBuildDependencies
```

Pré-requisitos de build: Windows, Python 3.13 na `.venv` e Inno Setup 6. O
computador que recebe o instalador não precisa ter Python instalado.

