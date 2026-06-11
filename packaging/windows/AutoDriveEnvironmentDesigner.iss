#ifndef RepoRoot
  #define RepoRoot "."
#endif

#define MyAppName "AutoDrive Environment Designer"
#define MyAppVersion "1.0.0-prototype"
#define MyAppPublisher "Kim Il Rae"
#define MyAppExeName "AutoDriveEnvironmentDesigner.exe"

[Setup]
AppId={{8A4B9E4E-8D4F-4BF1-8E5B-9F0D4D4B7A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir={#RepoRoot}\output\installer
OutputBaseFilename=AutoDriveEnvironmentDesigner_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕 화면 아이콘 만들기"; GroupDescription: "추가 아이콘:"

[Files]
Source: "{#RepoRoot}\dist\AutoDriveEnvironmentDesigner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall skipifsilent
