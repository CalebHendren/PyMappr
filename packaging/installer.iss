; Inno Setup script for the EzMaps Windows installer.
;
;   iscc packaging\installer.iss
;
; Expects the PyInstaller output in dist\EzMaps (see ezmaps.spec).
; The installer asks whether to create a desktop shortcut via the
; "desktopicon" task checkbox on the Select Additional Tasks page.

#define MyAppName "EzMaps"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "EzMaps"
#define MyAppExeName "EzMaps.exe"

[Setup]
AppId={{7E2F8C64-9C1B-4E8E-A9D1-3B54E210A96C}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist\installer
OutputBaseFilename=EzMaps-Setup-{#MyAppVersion}
SetupIconFile=..\data\icon\ezmaps.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Tasks]
; This is the "would you like to create a desktop shortcut?" question.
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\EzMaps\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent
