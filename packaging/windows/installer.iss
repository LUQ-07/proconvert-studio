; Inno Setup 6 script. Build: ISCC.exe /DAppVersion=1.0.0 packaging\windows\installer.iss
; NOT YET RUN (no Windows in the authoring environment).
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "ProConvert Studio"
#define AppExe "ProConvertStudio.exe"
#define Publisher "LUQ-07"

[Setup]
AppId={{c3276811-4df9-4938-8ca7-a8623352a0c6}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=ProConvertStudio-{#AppVersion}-setup
SetupIconFile=..\..\proconvert\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=LICENSE.txt
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\ProConvertStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

; The uninstaller removes the program files. User settings/history in %APPDATA% and %LOCALAPPDATA% are kept on purpose.
