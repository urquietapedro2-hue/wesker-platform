#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
[Setup]
AppId={{B6C1E0A2-5E55-4F6B-9C1D-0E5C0D1A7001}
AppName=WESKER
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\WESKER
DefaultGroupName=WESKER
PrivilegesRequired=lowest
OutputDir=..\dist_installer
OutputBaseFilename=WESKER-Setup
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=yes

[Files]
Source: "..\dist\WESKER\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\WESKER"; Filename: "{app}\WESKER.exe"
Name: "{autodesktop}\WESKER"; Filename: "{app}\WESKER.exe"

[Run]
Filename: "{app}\WESKER.exe"; Description: "Abrir WESKER"; Flags: nowait postinstall skipifsilent
