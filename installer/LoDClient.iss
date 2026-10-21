; Build recipe only. The payload contains an unmodified game and a prototype client.
; Compile with Inno Setup after running recovery_lab.bundle into runtime/package-v1.
[Setup]
AppId={{32E77CC3-9B62-40BA-88A3-1B370575D7B3}
AppName=LoD Recovery Prototype
AppVersion=0.1.0
DefaultDirName={localappdata}\LoDRecoveryPrototype
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=LoDRecovery-Prototype-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\Client\LoDClient.exe

[Files]
Source: "..\runtime\package-v1\Game\*"; DestDir: "{app}\Game"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\runtime\package-v1\Client\LoDClient.exe"; DestDir: "{app}\Client"; Flags: ignoreversion

[Icons]
Name: "{userdesktop}\LoD Client (Prototype)"; Filename: "{app}\Client\LoDClient.exe"
Name: "{userprograms}\LoD Client (Prototype)"; Filename: "{app}\Client\LoDClient.exe"
