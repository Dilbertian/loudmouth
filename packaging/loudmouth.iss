; Loudmouth — Inno Setup installer (consumer Windows package)
;
; Compile via packaging\build.ps1, which passes the version from server.py:
;     iscc /DAppVersion=<version> packaging\loudmouth.iss
;
; What this installer does:
;   - Installs the PyInstaller onedir build to %ProgramFiles%\Stark\Loudmouth
;   - Registers a per-user Task Scheduler logon entry (windowless — the exe
;     is built --noconsole, so no console window ever appears)
;   - Launches Loudmouth at installer finish
;   - Uninstall removes the scheduled task, stops the process, removes the
;     install dir and the per-user log dir — no leftovers
;   - Standard Inno silent flags work for fleet/enterprise use:
;       LoudmouthSetup-<ver>.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
;
; Known limitation (documented in README): a per-user logon task means
; Loudmouth runs only while that Windows user is logged in — correct for
; consumer machines.

#ifndef AppVersion
  #error Pass the version from server.py: iscc /DAppVersion=x.y.z packaging\loudmouth.iss (or use packaging\build.ps1)
#endif

#define AppName "Loudmouth"
#define Publisher "Stark Technologies"
#define AppExe "loudmouth.exe"
#define TaskName "Loudmouth Audio Server"

[Setup]
AppId={{7D0C2E5A-9C1B-4A57-B67D-1F45E9A0C3D8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL=https://github.com/Dilbertian/loudmouth
AppSupportURL=https://github.com/Dilbertian/loudmouth/issues
DefaultDirName={autopf}\Stark\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
LicenseFile=..\LICENSE
PrivilegesRequired=admin
OutputDir=..\dist
OutputBaseFilename=LoudmouthSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} Audio Server
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#Publisher}
VersionInfoDescription={#AppName} audio server installer

[Files]
Source: "..\dist\Loudmouth\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start menu entry (F15) — without it users hunt for the install and conclude
; nothing happened. The Comment surfaces as the tooltip: launch-on-login is
; already configured, clicking it is only needed after a manual stop.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; \
    Comment: "Audio server for IdeaLoom voice — starts automatically when you sign in; IdeaLoom finds it on its own."

[Messages]
; Visible install feedback (F14) — the app itself is headless.
FinishedLabel=Setup has finished installing [name] on your computer.%n%nLoudmouth is now running in the background — IdeaLoom will find it automatically. It also starts by itself each time you sign in to Windows.

[Run]
; Per-user logon task. schtasks runs elevated here; on a consumer machine the
; elevating user is the logged-in user, so the task registers for them.
; ONLOGON with the interactive token = starts at logon, only while that user
; is logged in, no credentials stored. /RL LIMITED: no reason to run elevated.
Filename: "{sys}\schtasks.exe"; \
    Parameters: "/Create /F /RL LIMITED /SC ONLOGON /TN ""{#TaskName}"" /TR """"""{app}\{#AppExe}"""""""; \
    Flags: runhidden; StatusMsg: "Registering logon task..."
; Auto-launch now (as the real desktop user, not the elevated installer user),
; so the consumer doesn't need to reboot before /health answers.
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; StatusMsg: "Starting Loudmouth..."

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /F /TN ""{#TaskName}"""; \
    Flags: runhidden; RunOnceId: "DelTask"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; \
    Flags: runhidden; RunOnceId: "KillProc"

[UninstallDelete]
; Per-user log dir (launcher.py writes %LOCALAPPDATA%\Loudmouth\loudmouth.log)
Type: filesandordirs; Name: "{localappdata}\Loudmouth"

[Code]
{ Stop a running instance before install so files aren't locked on upgrade. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;
