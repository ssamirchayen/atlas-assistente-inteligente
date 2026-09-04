# Sprint 26 — Build final do EXE e instalador

Objetivo: congelar o frontend Premium UI / Live Interface da Sprint 26 dentro do
`Atlas.exe` e gerar o instalador final do Atlas Core 1.0.0.

## O que este pacote faz

- mantém o entrypoint `gui_main.py`, portanto preserva o hotfix de instância única;
- força o PyInstaller a considerar explicitamente `orb`, `theme`,
  `single_instance` e `admin_console`;
- corrige a detecção do Inno Setup instalado no `%LOCALAPPDATA%`;
- mantém a exceção segura para o `certifi/cacert.pem` público;
- atualiza o instalador para Atlas Core 1.0.0 / NEXYRA, preservando o mesmo
  `AppId` para atualização da instalação anterior;
- adiciona uma pré-validação específica da Sprint 26;
- calcula SHA-256 do EXE e do instalador ao final.

## Aplicação

Extraia o ZIP na raiz de `C:\Atlas_OFICIAL` e aceite substituir os arquivos.

## Build recomendada

```powershell
cd C:\Atlas_OFICIAL
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\build_windows_installer.ps1
```

Se o PyInstaller não estiver instalado:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\build_windows_installer.ps1 -InstallBuildDependencies
```

## Saídas esperadas

- `C:\Atlas_OFICIAL\dist\Atlas\Atlas.exe`
- `C:\Atlas_OFICIAL\dist\installer\AtlasCoreSetup-1.0.0.exe`

## Aceitação do EXE

1. Abrir `dist\Atlas\Atlas.exe`.
2. Confirmar o frontend escuro da Sprint 26 com Atlas Pulse/orb.
3. Testar texto, microfone e escuta contínua.
4. Abrir calculadora pelo Atlas.
5. Testar Histórico e Admin Console.
6. Clicar várias vezes no `Atlas.exe`: deve permanecer uma única janela.
7. Fechar e reabrir normalmente.

## Aceitação do instalador

1. Desinstalar a build anterior somente depois de preservar dados que queira
   manter.
2. Instalar `AtlasCoreSetup-1.0.0.exe`.
3. Marcar "Iniciar o Atlas Core".
4. Confirmar que abre uma única janela com o novo frontend.
5. Testar o atalho da Área de Trabalho e o Menu Iniciar.

Somente depois dessa validação a Sprint 26 deve ser congelada para o push
consolidado das Sprints 24, 25 e 26.
