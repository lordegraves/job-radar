#define AppName "Junior"
#define AppVersion "0.2.0"
#define BuildLabel "RC6 Build 1.8"
#define BuildSlug "RC6-build-1.8"
#define AppPublisher "Junior"
#define AppExeName "Junior.exe"

[Setup]
AppId={{CB6B32BA-8BC0-4CC0-A14D-0C12864035B1}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion} - {#BuildLabel}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Junior
DefaultGroupName=Junior
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\artifacts\installer
OutputBaseFilename=Junior-Setup-{#AppVersion}-{#BuildSlug}
SetupIconFile=..\..\job_radar\static\junior.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Junior's external update handoff waits for the desktop process to exit.
; Restart Manager must not force-close pywebview/.NET processes during setup.
CloseApplications=no
RestartApplications=no
ChangesEnvironment=no

[InstallDelete]
; PyInstaller's _internal directory is application-owned. Replace it as one
; unit so removed dependencies from an older build cannot survive an upgrade
; and collide with the new executable. User data is stored elsewhere.
Type: filesandordirs; Name: "{app}\_internal"

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
Filename: "{app}\{#AppExeName}"; Description: "Launch Junior"; Flags: nowait postinstall; Check: ShouldOfferInteractiveLaunch
Filename: "{app}\{#AppExeName}"; Flags: nowait; Check: IsAutomaticUpdate

[Code]
function IsAutomaticUpdate(): Boolean;
var
  Index: Integer;
begin
  Result := False;
  for Index := 1 to ParamCount do
    if CompareText(ParamStr(Index), '/AUTOLAUNCH') = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

function ShouldOfferInteractiveLaunch(): Boolean;
begin
  { Interactive installs retain the normal launch checkbox. Automatic updates
    use their own unconditional run entry after the silent install succeeds. }
  Result := (not WizardSilent) and (not IsAutomaticUpdate());
end;

function InitializeSetup(): Boolean;
begin
  { User data lives under LocalAppData\JobRadar and is deliberately outside
    the installation directory. Setup and uninstall never remove that data. }
  Result := True;
end;
