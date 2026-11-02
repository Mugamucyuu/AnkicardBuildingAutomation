#ifndef AppVersion
  #error AppVersion must be provided by tools/build_windows.ps1
#endif
#ifndef WebViewInstaller
  #error WebViewInstaller must point to the signed x64 standalone installer
#endif
#define RepoRoot AddBackslash(SourcePath) + "..\.."

[Setup]
AppId={{3E9CFC2A-A5A2-460C-9C63-26DF955A17E4}
AppName=Ankicard Building Automation
AppVersion={#AppVersion}
AppPublisher=Mugamucyuu
AppPublisherURL=https://github.com/Mugamucyuu/AnkicardBuildingAutomation
AppSupportURL=https://github.com/Mugamucyuu/AnkicardBuildingAutomation/issues
AppUpdatesURL=https://github.com/Mugamucyuu/AnkicardBuildingAutomation/releases
DefaultDirName={localappdata}\Programs\Ankicard
DefaultGroupName=Ankicard Building Automation
UsePreviousAppDir=yes
UsePreviousTasks=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
DisableProgramGroupPage=yes
LicenseFile={#RepoRoot}\LICENSE
OutputDir={#RepoRoot}\dist\windows
OutputBaseFilename=Ankicard-{#AppVersion}-windows-x64-Setup
SetupIconFile=ankicard.ico
UninstallDisplayIcon={app}\Ankicard.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupMutex=AnkicardSetup

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "{#RepoRoot}\dist\Ankicard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#WebViewInstaller}"; DestName: "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Flags: dontcopy

[Icons]
Name: "{group}\Ankicard"; Filename: "{app}\Ankicard.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Ankicard"; Filename: "{app}\Ankicard.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Ankicard.exe"; Description: "Open Ankicard"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebViewKey = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{3E9CFC2A-A5A2-460C-9C63-26DF955A17E4}_is1';

function NextVersionPart(var Value: String): Integer;
var
  P: Integer;
begin
  P := Pos('.', Value);
  if P = 0 then begin
    Result := StrToIntDef(Value, 0);
    Value := '';
  end else begin
    Result := StrToIntDef(Copy(Value, 1, P - 1), 0);
    Delete(Value, 1, P);
  end;
end;

function IsNewerVersion(Installed, Candidate: String): Boolean;
var
  I, A, B: Integer;
begin
  Result := False;
  for I := 1 to 3 do begin
    A := NextVersionPart(Installed);
    B := NextVersionPart(Candidate);
    if A <> B then begin
      Result := A > B;
      Exit;
    end;
  end;
end;

function InitializeSetup: Boolean;
var
  Installed: String;
begin
  Result := True;
  if RegQueryStringValue(HKCU64, UninstallKey, 'DisplayVersion', Installed) then
    if IsNewerVersion(Installed, '{#AppVersion}') then begin
      SuppressibleMsgBox('A newer version of Ankicard is already installed. Please use the latest installer.', mbError, MB_OK, IDOK);
      Result := False;
    end;
end;

function HasRuntime: Boolean;
var
  Version: String;
begin
  Result := (RegQueryStringValue(HKLM32, WebViewKey, 'pv', Version) and
    (Version <> '') and (Version <> '0.0.0.0'));
  if not Result then
    Result := (RegQueryStringValue(HKCU32, WebViewKey, 'pv', Version) and
      (Version <> '') and (Version <> '0.0.0.0'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if not HasRuntime then begin
    ExtractTemporaryFile('MicrosoftEdgeWebView2RuntimeInstallerX64.exe');
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'),
      '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      Result := 'Unable to install Microsoft WebView2. Please retry Setup.'
    else if not HasRuntime then
      Result := Format('Microsoft WebView2 installation did not complete (code %d). Please retry Setup.', [ExitCode]);
  end;
end;

// Deliberately no UninstallDelete: user preferences, prompts and jobs survive upgrades/uninstall.
