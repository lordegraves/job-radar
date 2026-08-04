#define AppName "Junior"
#define AppVersion "0.2.0"
#define BuildLabel "RC6 Build 1.11"
#define BuildSlug "RC6-build-1.11"
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
WizardImageFile=..\..\job_radar\static\junior_wizard.png
WizardSmallImageFile=..\..\job_radar\static\junior_icon_v2.png
WizardImageBackColor=$000000
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

[Registry]
Root: HKCU; Subkey: "Software\Junior"; ValueType: string; ValueName: "InstalledBuild"; ValueData: "{#BuildLabel}"; Flags: uninsdeletekeyifempty uninsdeletevalue

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Junior"; Flags: nowait postinstall; Check: ShouldOfferInteractiveLaunch
Filename: "{app}\{#AppExeName}"; Flags: nowait; Check: IsAutomaticUpdate

[Code]
const
  SetupModeInstall = 0;
  SetupModeUpdate = 1;
  SetupModeRepair = 2;
  JuniorUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{CB6B32BA-8BC0-4CC0-A14D-0C12864035B1}_is1';

var
  JuniorSetupMode: Integer;

procedure ApplyJuniorTheme();
var
  Index: Integer;
begin
  { Match Junior's application palette while leaving native Windows buttons
    untouched so keyboard, focus, and high-contrast behavior stay reliable. }
  WizardForm.Color := $0010100F;
  WizardForm.MainPanel.Color := $00191717;
  WizardForm.WelcomePage.Color := $0010100F;
  WizardForm.InnerPage.Color := $0010100F;
  WizardForm.FinishedPage.Color := $0010100F;
  WizardForm.WelcomeLabel1.Font.Color := $00F3F3F3;
  WizardForm.WelcomeLabel2.Font.Color := $00C2B7B7;
  WizardForm.PageNameLabel.Font.Color := $00F3F3F3;
  WizardForm.PageDescriptionLabel.Font.Color := $00C2B7B7;
  WizardForm.FinishedHeadingLabel.Font.Color := $00F3F3F3;
  WizardForm.FinishedLabel.Font.Color := $00C2B7B7;

  { Inno creates many page-specific labels and task controls with the normal
    light-theme text color. Apply the readable foreground to every matching
    wizard control so later pages do not render dark text on a dark surface. }
  for Index := 0 to WizardForm.ComponentCount - 1 do
  begin
    if WizardForm.Components[Index] is TNewStaticText then
      TNewStaticText(WizardForm.Components[Index]).Font.Color := $00F3F3F3
    else if WizardForm.Components[Index] is TNewCheckBox then
      TNewCheckBox(WizardForm.Components[Index]).Font.Color := $00F3F3F3
    else if WizardForm.Components[Index] is TNewRadioButton then
      TNewRadioButton(WizardForm.Components[Index]).Font.Color := $00F3F3F3
    else if WizardForm.Components[Index] is TNewCheckListBox then
    begin
      TNewCheckListBox(WizardForm.Components[Index]).Color := $00171515;
      TNewCheckListBox(WizardForm.Components[Index]).Font.Color := $00F3F3F3;
    end;
  end;
end;

function DetectSetupMode(): Integer;
var
  InstalledBuild: String;
  InstalledDisplayName: String;
begin
  if RegQueryStringValue(HKCU, 'Software\Junior', 'InstalledBuild', InstalledBuild) then
  begin
    if CompareText(InstalledBuild, '{#BuildLabel}') = 0 then
      Result := SetupModeRepair
    else
      Result := SetupModeUpdate;
    Exit;
  end;

  if RegQueryStringValue(HKCU, JuniorUninstallKey, 'DisplayName', InstalledDisplayName) then
  begin
    if Pos('{#BuildLabel}', InstalledDisplayName) > 0 then
      Result := SetupModeRepair
    else
      Result := SetupModeUpdate;
    Exit;
  end;

  Result := SetupModeInstall;
end;

function SetupActionName(): String;
begin
  case JuniorSetupMode of
    SetupModeUpdate: Result := 'Update';
    SetupModeRepair: Result := 'Repair';
  else
    Result := 'Install';
  end;
end;

procedure InitializeWizard();
var
  ActionName: String;
begin
  JuniorSetupMode := DetectSetupMode();
  ApplyJuniorTheme();
  ActionName := SetupActionName();
  WizardForm.Caption := ActionName + ' - Junior {#AppVersion} - {#BuildLabel}';
  WizardForm.WelcomeLabel1.Caption := 'Welcome to the Junior ' + ActionName + ' Wizard';
  if JuniorSetupMode = SetupModeInstall then
    WizardForm.WelcomeLabel2.Caption :=
      'This wizard will install Junior on your computer.'
  else if JuniorSetupMode = SetupModeUpdate then
    WizardForm.WelcomeLabel2.Caption :=
      'This wizard will update the existing Junior installation while preserving your settings and data.'
  else
    WizardForm.WelcomeLabel2.Caption :=
      'This wizard will repair the existing Junior installation while preserving your settings and data.';
end;

procedure CurPageChanged(CurPageID: Integer);
var
  ActionName: String;
begin
  ActionName := SetupActionName();
  if CurPageID = wpReady then
    WizardForm.NextButton.Caption := '&' + ActionName
  else if CurPageID = wpFinished then
  begin
    WizardForm.FinishedHeadingLabel.Caption :=
      'Completing the Junior ' + ActionName + ' Wizard';
    if JuniorSetupMode = SetupModeInstall then
      WizardForm.FinishedLabel.Caption :=
        'Junior was installed successfully. Click Finish to exit Setup.'
    else if JuniorSetupMode = SetupModeUpdate then
      WizardForm.FinishedLabel.Caption :=
        'Junior was updated successfully. Your settings and data were preserved. Click Finish to exit Setup.'
    else
      WizardForm.FinishedLabel.Caption :=
        'Junior was repaired successfully. Your settings and data were preserved. Click Finish to exit Setup.';
  end;
end;

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
