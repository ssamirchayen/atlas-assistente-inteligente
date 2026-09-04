#define MyAppName "Atlas Core"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "NEXYRA"
#define MyAppExeName "Atlas.exe"
#ifndef SourceDir
  #define SourceDir "..\..\dist\Atlas"
#endif

[Setup]
AppId={{9C4A7189-12CC-4F89-83D8-A57651E6ECA4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Atlas
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist\installer
OutputBaseFilename=AtlasCoreSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Dirs]
Name: "{localappdata}\Atlas"; Flags: uninsneveruninstall
Name: "{localappdata}\Atlas\data"; Flags: uninsneveruninstall
Name: "{localappdata}\Atlas\logs"; Flags: uninsneveruninstall

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\.env.example"; DestDir: "{localappdata}\Atlas"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Iniciar o Atlas Core"; Flags: nowait postinstall skipifsilent
