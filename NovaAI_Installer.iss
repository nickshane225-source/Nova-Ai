; Script generated for Inno Setup Compiler
; To create NovaAI_Setup.exe:
; 1. Download and install Inno Setup (free) from https://jrsoftware.org/isdl.php
; 2. Open this file in Inno Setup and click "Compile" (or press Ctrl+F9)

#define MyAppName "Nova AI"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Nova AI"
#define MyAppExeName "NovaAI.exe"

[Setup]
AppId={{9B7C72B1-4A59-4D88-B31F-C86901A79BEE}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={userpf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=NovaAI_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\NovaAI.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "data\characters.json"; DestDir: "{app}\data"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
