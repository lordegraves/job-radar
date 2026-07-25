#define AppName "Junior"
#define AppVersion "0.2.0"
#define AppPublisher "Junior"
#define AppExeName "Junior.exe"

[Setup]
AppId={{CB6B32BA-8BC0-4CC0-A14D-0C12864035B1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Junior
DefaultGroupName=Junior
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\artifacts\installer
OutputBaseFilename=Junior-Setup-{#AppVersion}
SetupIconFile=..\..\job_radar\static\junior.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ChangesEnvironment=no

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\artifacts\windows\Junior\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\PRIVACY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\SECURITY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\THIRD_PARTY_LICENSES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dependency-license-report.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\third_party\*"; DestDir: "{app}\third_party"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Junior"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\Junior"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Junior"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  { User data lives under LocalAppData\JobRadar and is deliberately outside
    the installation directory. Setup and uninstall never remove that data. }
  Result := True;
end;
