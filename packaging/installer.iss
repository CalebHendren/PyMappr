; Inno Setup script for the PyMappr Windows installer.
;
;   iscc packaging\installer.iss
;
; Expects the PyInstaller output in dist\PyMappr (see pymappr.spec).
; The installer asks whether to create a desktop shortcut via the
; "desktopicon" task checkbox on the Select Additional Tasks page.
;
; Uninstall: when an existing installation is found (including one made
; under the old EzMaps name - the AppId is unchanged), the wizard offers
; to uninstall it instead of installing, so the same setup program also
; serves as the uninstaller entry point. A Start-menu "Uninstall PyMappr"
; shortcut is created as well.

#define MyAppName "PyMappr"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "PyMappr"
#define MyAppExeName "PyMappr.exe"

[Setup]
AppId={{7E2F8C64-9C1B-4E8E-A9D1-3B54E210A96C}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist\installer
OutputBaseFilename=PyMappr-Setup-{#MyAppVersion}
SetupIconFile=..\data\icon\pymappr.ico
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
Source: "..\dist\PyMappr\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent

[Code]
// The uninstall registry key Inno Setup writes for this AppId.
const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
                 '{7E2F8C64-9C1B-4E8E-A9D1-3B54E210A96C}_is1';

function GetUninstallString(): String;
begin
  Result := '';
  if not RegQueryStringValue(HKLM, UninstallKey, 'UninstallString', Result)
  then
    RegQueryStringValue(HKCU, UninstallKey, 'UninstallString', Result);
end;

function InitializeSetup(): Boolean;
var
  Uninstaller: String;
  Choice, ResultCode: Integer;
begin
  Result := True;
  Uninstaller := GetUninstallString();
  if Uninstaller = '' then
    exit;
  Choice := MsgBox(
    'An existing installation of {#MyAppName} was found.' + #13#10 + #13#10 +
    'Yes - uninstall it now and close this wizard.' + #13#10 +
    'No - keep it and continue installing (update it).' + #13#10 +
    'Cancel - close this wizard without changing anything.',
    mbConfirmation, MB_YESNOCANCEL);
  if Choice = IDCANCEL then
    Result := False
  else if Choice = IDYES then
  begin
    Exec(RemoveQuotes(Uninstaller), '', '', SW_SHOW,
         ewWaitUntilTerminated, ResultCode);
    Result := False;
  end;
end;
