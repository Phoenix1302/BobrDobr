; =====================================================================
; BobrDobr VPN - Inno Setup 6 Installer Script
; Targets: Windows 10 / Windows 11 (64-bit)
; System-level Program Files (64-bit) Installation (Admin Elevation Required)
; =====================================================================

#ifndef AppId
  #define AppId "{{A71F6C91-499B-4D78-8BF4-7662BD7EE652}"
#endif

#ifndef AppName
  #define AppName "БобрДобр VPN"
#endif

#ifndef AppEnglishName
  #define AppEnglishName "BobrDobr VPN"
#endif

#ifndef AppVersion
  #define AppVersion "1.3.0"
#endif

#ifndef AppPublisher
  #define AppPublisher "BobrDobr Hydro-engineering Team"
#endif

#ifndef AppPublisherURL
  #define AppPublisherURL "https://github.com/Phoenix1302/BobrDobr"
#endif

#ifndef AppSupportURL
  #define AppSupportURL "https://github.com/Phoenix1302/BobrDobr/issues"
#endif

#ifndef AppUpdatesURL
  #define AppUpdatesURL "https://github.com/Phoenix1302/BobrDobr/releases"
#endif

#ifndef AppExeName
  #define AppExeName "BobrDobr.exe"
#endif

#ifndef SourceDir
  #define SourceDir "..\..\..\.."
#endif

#ifndef BinDir
  #define BinDir SourceDir + "\bin\windows"
#endif

#ifndef AssetsDir
  #define AssetsDir SourceDir + "\assets"
#endif

#ifndef CertsDir
  #define CertsDir SourceDir + "\client-go\certs"
#endif

#ifndef OutputDir
  #define OutputDir "Output"
#endif

#ifndef AppExeSource
  #if FileExists(SourceDir + "\dist\windows\BobrDobr.exe")
    #define AppExeSource SourceDir + "\dist\windows\BobrDobr.exe"
  #elif FileExists(SourceDir + "\dist\windows\BobrDobr-VPN-v1.1.1.exe")
    #define AppExeSource SourceDir + "\dist\windows\BobrDobr-VPN-v1.1.1.exe"
  #elif FileExists(SourceDir + "\client-go\BobrDobr.exe")
    #define AppExeSource SourceDir + "\client-go\BobrDobr.exe"
  #elif FileExists("BobrDobr.exe")
    #define AppExeSource "BobrDobr.exe"
  #else
    #define AppExeSource SourceDir + "\dist\windows\BobrDobr.exe"
  #endif
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppPublisherURL}
AppSupportURL={#AppSupportURL}
AppUpdatesURL={#AppUpdatesURL}

; Target installation folder: C:\Program Files\BobrDobr (Requires Administrator)
DefaultDirName={commonpf64}\BobrDobr
DisableWelcomePage=no
DisableDirPage=no
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; Requires administrative elevation for proper Wintun virtual network adapter installation
; Do not allow user dialog overrides to avoid dual/split installations
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
UsedUserAreasWarning=no

; Output settings
OutputDir={#OutputDir}
OutputBaseFilename=BobrDobr-Setup-v{#AppVersion}
SetupIconFile={#AssetsDir}\bobr_logo.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

; Compression
Compression=lzma2/ultra64
SolidCompression=yes
InternalCompressLevel=ultra64

; Target Architecture (x64 Windows)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; UI & Style
WizardStyle=modern
ShowLanguageDialog=auto

; Single Instance Detection via Mutex
AppMutex=Global\BobrDobr_VPN_SingleInstance_Unified_v1,BobrDobr_VPN_SingleInstance_Unified_v1
CloseApplications=force
CloseApplicationsFilter=*.exe

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
russian.BeveledLabel=БобрДобр VPN Инсталлятор
english.BeveledLabel=BobrDobr VPN Installer

[CustomMessages]
russian.CreateDesktopIcon=Создать значок на &Рабочем столе
english.CreateDesktopIcon=Create a &desktop shortcut
russian.AutoStartProgram=Запускать {#AppName} при входе в систему
english.AutoStartProgram=Start {#AppEnglishName} when Windows starts
russian.LaunchProgram=Запустить {#AppName} сейчас
english.LaunchProgram=Launch {#AppEnglishName} now
russian.CleanAppDataPrompt=Удалить все сохранённые профили подключения, логи и кэш BobrDobr VPN?%n%nПапка данных: %1
english.CleanAppDataPrompt=Do you want to completely remove all saved VPN profiles, logs, and cache?%n%nData folder: %1
russian.AppRunningUninstall=Приложение {#AppName} сейчас запущено.%nПожалуйста, закройте приложение перед продолжением удаления.
english.AppRunningUninstall={#AppEnglishName} is currently running.%nPlease close the application before proceeding with uninstallation.
russian.UpgradeDetected=Обнаружена ранее установленная версия {#AppName} (%1).%n%nМастер выполнит быстрое обновление до версии {#AppVersion}. Все ваши подключения, подписки и настройки будут надёжно сохранены.
english.UpgradeDetected=A previous version of {#AppEnglishName} (%1) was detected.%n%nSetup will update to version {#AppVersion}. All your VPN profiles, subscriptions, and settings will be safely preserved.
russian.CloseRunningAppPrompt=Приложение {#AppName} сейчас запущено.%nДля продолжения обновления оно будет закрыто.%n%nЗакрыть приложение и продолжить установку?
english.CloseRunningAppPrompt=The application {#AppEnglishName} is currently running.%nIt must be closed to proceed with the update.%n%nClose the application and continue?

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "{cm:AutoStartProgram}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main Executable
Source: "{#AppExeSource}"; DestDir: "{app}"; DestName: "{#AppExeName}"; Flags: ignoreversion

; Embedded Application Manifest (alongside binary for standalone resolution if needed)
Source: "..\manifest\BobrDobr.exe.manifest"; DestDir: "{app}"; DestName: "{#AppExeName}.manifest"; Flags: ignoreversion

; Core VPN engines and networking drivers (stored single-instance in {app}\bin)
Source: "{#BinDir}\amneziawg-go.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "{#BinDir}\openconnect-worker.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "{#BinDir}\wintun.dll"; DestDir: "{app}\bin"; Flags: ignoreversion

; UI Assets and Icons
Source: "{#AssetsDir}\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AssetsDir}\bobr_logo.ico"; DestDir: "{app}"; Flags: ignoreversion

; Public security certificates for Windows trust
Source: "{#CertsDir}\BobrDobr-RootCA.cer"; DestDir: "{app}\certs"; Flags: ignoreversion
Source: "{#CertsDir}\BobrDobr-CodeSign.cer"; DestDir: "{app}\certs"; Flags: ignoreversion

[InstallDelete]
; Clean up legacy C-libraries, openconnect.exe and vpnc scripts from older BobrDobr installations
Type: files; Name: "{app}\bin\openconnect.exe"
Type: files; Name: "{app}\bin\vpnc-script-win.js"
Type: files; Name: "{app}\bin\vpnc-script.js"
Type: files; Name: "{app}\bin\lib*.dll"
Type: files; Name: "{app}\bin\zlib1.dll"
Type: filesandordirs; Name: "{app}\bin\windows"
Type: files; Name: "{app}\wintun.dll"
; Proactively purge legacy user-level installation folder to eliminate duplicate copies
Type: filesandordirs; Name: "{localappdata}\Programs\BobrDobr"
; Proactively purge legacy user-level shortcuts and folders pointing to localappdata
Type: files; Name: "{userdesktop}\{#AppName}.lnk"
Type: files; Name: "{userdesktop}\{#AppEnglishName}.lnk"
Type: files; Name: "{userdesktop}\BobrDobr.lnk"
Type: files; Name: "{userdesktop}\BobrDobr-VPN.lnk"
Type: files; Name: "{userprograms}\{#AppName}.lnk"
Type: files; Name: "{userprograms}\{#AppEnglishName}.lnk"
Type: files; Name: "{userprograms}\BobrDobr.lnk"
Type: files; Name: "{userprograms}\BobrDobr-VPN.lnk"
Type: filesandordirs; Name: "{userprograms}\{#AppName}"
Type: filesandordirs; Name: "{userprograms}\{#AppEnglishName}"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\bin"
Type: filesandordirs; Name: "{app}\assets"
Type: filesandordirs; Name: "{app}\certs"
Type: files; Name: "{userdesktop}\{#AppName}.lnk"
Type: files; Name: "{userdesktop}\{#AppEnglishName}.lnk"
Type: files; Name: "{userdesktop}\BobrDobr.lnk"
Type: files; Name: "{userdesktop}\BobrDobr-VPN.lnk"
Type: files; Name: "{userprograms}\{#AppName}.lnk"
Type: files; Name: "{userprograms}\{#AppEnglishName}.lnk"
Type: files; Name: "{userprograms}\BobrDobr.lnk"
Type: files; Name: "{userprograms}\BobrDobr-VPN.lnk"
Type: filesandordirs; Name: "{userprograms}\{#AppName}"
Type: filesandordirs; Name: "{userprograms}\{#AppEnglishName}"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\bobr_logo.ico"; WorkingDir: "{app}"; AppUserModelID: "BobrDobr.VPN.Client"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\bobr_logo.ico"; WorkingDir: "{app}"; AppUserModelID: "BobrDobr.VPN.Client"; Tasks: desktopicon

[Registry]
; Auto-start: HKLM for all-users / HKCU for current-user
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "BobrDobrVPN"; ValueData: """{app}\{#AppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart
; Application registration for Windows App Paths
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExeName}"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey
; AppUserModelID registration for Windows Action Center and notification titles
Root: HKA; Subkey: "Software\Classes\AppUserModelId\BobrDobr.VPN.Client"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AppUserModelId\BobrDobr.VPN.Client"; ValueType: string; ValueName: "IconUri"; ValueData: "{app}\assets\bobr_logo.ico"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AppUserModelId\BobrDobr.VPN.Client"; ValueType: string; ValueName: "IconBackgroundColor"; ValueData: "0"; Flags: uninsdeletekey
; Protocol registration for interactive notifications (bobrdobr://...)
Root: HKA; Subkey: "Software\Classes\bobrdobr"; ValueType: string; ValueName: ""; ValueData: "URL:BobrDobr Protocol"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\bobrdobr"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\bobrdobr\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Flags: uninsdeletekey

[Run]
; Register BobrDobr Root CA into Trusted Root Certification Authorities and Code Signing into Trusted Publishers
Filename: "{sys}\certutil.exe"; Parameters: "-addstore -f Root ""{app}\certs\BobrDobr-RootCA.cer"""; Flags: runhidden
Filename: "{sys}\certutil.exe"; Parameters: "-addstore -f TrustedPublisher ""{app}\certs\BobrDobr-CodeSign.cer"""; Flags: runhidden
; Whitelist VPN core daemons in Windows Firewall to prevent any firewall prompt popups
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""BobrDobr AmneziaWG"" dir=in action=allow program=""{app}\bin\amneziawg-go.exe"" enable=yes profile=any"; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""BobrDobr OpenConnect"" dir=in action=allow program=""{app}\bin\openconnect-worker.exe"" enable=yes profile=any"; Flags: runhidden
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram}"; Flags: shellexec nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\certutil.exe"; Parameters: "-delstore Root 8BE32AF4F6E0E7B1431C24522611ECBBB8BA5189"; Flags: runhidden; RunOnceId: "DelCertRoot"
Filename: "{sys}\certutil.exe"; Parameters: "-delstore TrustedPublisher 1F9FDC89219B37C82FFE0567AFB27BA5B001B4F5"; Flags: runhidden; RunOnceId: "DelCertPublisher"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""BobrDobr AmneziaWG"""; Flags: runhidden; RunOnceId: "DelFwRuleAmneziaWG"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""BobrDobr-AmneziaWG"""; Flags: runhidden; RunOnceId: "DelFwRuleAmneziaWGHyphen"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""BobrDobr OpenConnect"""; Flags: runhidden; RunOnceId: "DelFwRuleOpenConnect"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""BobrDobr-OpenConnect"""; Flags: runhidden; RunOnceId: "DelFwRuleOpenConnectHyphen"

[Code]
const
  HWND_TOPMOST = -1;
  SWP_NOSIZE = $0001;
  SWP_NOMOVE = $0002;
  SWP_SHOWWINDOW = $0040;

function SetWindowPos(hWnd: HWND; hWndInsertAfter: HWND; X, Y, cx, cy: Integer; uFlags: UINT): BOOL;
  external 'SetWindowPos@user32.dll stdcall';
function SetForegroundWindow(hWnd: HWND): BOOL;
  external 'SetForegroundWindow@user32.dll stdcall';
function BringWindowToTop(hWnd: HWND): BOOL;
  external 'BringWindowToTop@user32.dll stdcall';

var
  IsUpgradeMode: Boolean;
  PreviousVersion: String;
  PreviousInstallDir: String;

// Helper: Brings the installer wizard window to foreground and sets topmost
procedure MakeWizardTopMost();
begin
  BringWindowToTop(WizardForm.Handle);
  SetForegroundWindow(WizardForm.Handle);
  SetWindowPos(WizardForm.Handle, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE or SWP_NOSIZE or SWP_SHOWWINDOW);
end;

// Helper: Exhaustively purges all BobrDobr keys and values from a specific registry hive
procedure PurgeAllBobrDobrRegistryKeysFromHive(RootKey: Integer);
begin
  // 1. Application-level settings and configuration keys
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\BobrDobr');
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\BobrDobrVPN');
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\BobrDobr VPN');

  // 2. Uninstall registry subkeys (both standard single-brace and literal double-brace forms)
  RegDeleteKeyIncludingSubkeys(RootKey, ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}_is1'));
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}_is1');
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\BobrDobr_is1');
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\BobrDobr');
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\BobrDobr VPN_is1');
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\BobrDobr VPN');

  // 3. Application registration for Windows App Paths
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExeName}');
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\Microsoft\Windows\CurrentVersion\App Paths\BobrDobr.exe');
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\Microsoft\Windows\CurrentVersion\App Paths\BobrDobr-VPN.exe');

  // 4. Auto-start Run values & StartupApproved
  RegDeleteValue(RootKey, 'Software\Microsoft\Windows\CurrentVersion\Run', 'BobrDobrVPN');
  RegDeleteValue(RootKey, 'Software\Microsoft\Windows\CurrentVersion\Run', 'BobrDobr');
  RegDeleteValue(RootKey, 'Software\Microsoft\Windows\CurrentVersion\Run', 'BobrDobr-VPN');
  RegDeleteValue(RootKey, 'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run', 'BobrDobrVPN');
  RegDeleteValue(RootKey, 'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run', 'BobrDobr');
  RegDeleteValue(RootKey, 'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run', 'BobrDobr-VPN');

  // 5. AppUserModelId
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\Classes\AppUserModelId\BobrDobr.VPN.Client');

  // 6. bobrdobr:// protocol
  RegDeleteKeyIncludingSubkeys(RootKey, 'Software\Classes\bobrdobr');
end;

// Helper: Checks a specific registry root key for an existing installation and verifies files exist on disk
function CheckHiveForValidInstall(RootKey: Integer; const SubKey: String; var OutVer: String; var OutDir: String): Boolean;
var
  VerStr, DirStr: String;
  ExePath: String;
begin
  Result := False;
  VerStr := '';
  DirStr := '';

  if RegQueryStringValue(RootKey, SubKey, 'DisplayVersion', VerStr) then
  begin
    if not RegQueryStringValue(RootKey, SubKey, 'InstallLocation', DirStr) or (DirStr = '') then
      RegQueryStringValue(RootKey, SubKey, 'Inno Setup: App Path', DirStr);

    DirStr := RemoveQuotes(Trim(DirStr));
    if DirStr <> '' then
    begin
      ExePath := AddBackslash(DirStr) + '{#AppExeName}';
      if FileExists(ExePath) or FileExists(AddBackslash(DirStr) + 'BobrDobr-VPN.exe') or FileExists(AddBackslash(DirStr) + 'BobrDobr-VPN-v1.1.1.exe') then
      begin
        OutVer := VerStr;
        OutDir := DirStr;
        Result := True;
        Exit;
      end;
    end;

    // If DisplayVersion was found in registry but no executable exists on disk,
    // this is an orphaned/stale uninstall key left behind from previous manual or partial removal.
    // Clean it up proactively so Windows Installed Apps list and Setup remain clean.
    PurgeAllBobrDobrRegistryKeysFromHive(RootKey);
  end;
end;

// Helper: Checks registry for existing BobrDobr installation in HKLM (64/32-bit) and HKCU
function DetectExistingInstallation(var OutVersion: String; var OutInstallDir: String): Boolean;
var
  SubKeySingle, SubKeyDouble: String;
begin
  Result := False;
  OutVersion := '';
  OutInstallDir := '';

  // Standard Inno Setup single-brace key (resolved via ExpandConstant)
  SubKeySingle := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}_is1');
  // Literal double-brace key in case created by unescaped macro
  SubKeyDouble := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}_is1';

  // 1. Try HKLM 64-bit
  if CheckHiveForValidInstall(HKLM64, SubKeySingle, OutVersion, OutInstallDir) or
     CheckHiveForValidInstall(HKLM64, SubKeyDouble, OutVersion, OutInstallDir) then
    Result := True
  // 2. Try HKLM 32-bit
  else if CheckHiveForValidInstall(HKLM32, SubKeySingle, OutVersion, OutInstallDir) or
          CheckHiveForValidInstall(HKLM32, SubKeyDouble, OutVersion, OutInstallDir) then
    Result := True
  // 3. Try HKCU 64-bit
  else if CheckHiveForValidInstall(HKCU64, SubKeySingle, OutVersion, OutInstallDir) or
          CheckHiveForValidInstall(HKCU64, SubKeyDouble, OutVersion, OutInstallDir) then
    Result := True
  // 4. Try HKCU (standard / 32-bit)
  else if CheckHiveForValidInstall(HKCU, SubKeySingle, OutVersion, OutInstallDir) or
          CheckHiveForValidInstall(HKCU, SubKeyDouble, OutVersion, OutInstallDir) then
    Result := True;
end;

// Helper: Closes running instances of BobrDobr and VPN engines gracefully or forcefully
procedure TerminateRunningInstances();
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM BobrDobr.exe /IM BobrDobr-VPN.exe /IM BobrDobr-VPN-v1.1.0.exe /IM BobrDobr-VPN-v1.1.1.exe /IM amneziawg-go.exe /IM openconnect.exe /IM openconnect-worker.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(400);
end;

// Helper: Proactively purges legacy user-level installation (%LOCALAPPDATA%\Programs\BobrDobr) and shortcuts
procedure PurgeLegacyUserInstallation();
var
  LegacyUserDir: String;
  LegacyDesktopRu, LegacyDesktopEn: String;
  LegacyProgramsRu, LegacyProgramsEn: String;
  LegacyGroupRu, LegacyGroupEn: String;
begin
  // Terminate any running instances first so files are unlocked
  TerminateRunningInstances();

  // 1. Delete legacy user installation directory (%LOCALAPPDATA%\Programs\BobrDobr)
  LegacyUserDir := ExpandConstant('{localappdata}\Programs\BobrDobr');
  if DirExists(LegacyUserDir) then
  begin
    DelTree(LegacyUserDir, True, True, True);
  end;

  // 2. Delete legacy per-user desktop shortcuts
  LegacyDesktopRu := ExpandConstant('{userdesktop}\{#AppName}.lnk');
  LegacyDesktopEn := ExpandConstant('{userdesktop}\{#AppEnglishName}.lnk');
  if FileExists(LegacyDesktopRu) then
    DeleteFile(LegacyDesktopRu);
  if FileExists(LegacyDesktopEn) then
    DeleteFile(LegacyDesktopEn);
  if FileExists(ExpandConstant('{userdesktop}\BobrDobr.lnk')) then
    DeleteFile(ExpandConstant('{userdesktop}\BobrDobr.lnk'));
  if FileExists(ExpandConstant('{userdesktop}\BobrDobr-VPN.lnk')) then
    DeleteFile(ExpandConstant('{userdesktop}\BobrDobr-VPN.lnk'));

  // 3. Delete legacy per-user start menu shortcuts and folder
  LegacyProgramsRu := ExpandConstant('{userprograms}\{#AppName}.lnk');
  LegacyProgramsEn := ExpandConstant('{userprograms}\{#AppEnglishName}.lnk');
  if FileExists(LegacyProgramsRu) then
    DeleteFile(LegacyProgramsRu);
  if FileExists(LegacyProgramsEn) then
    DeleteFile(LegacyProgramsEn);
  if FileExists(ExpandConstant('{userprograms}\BobrDobr.lnk')) then
    DeleteFile(ExpandConstant('{userprograms}\BobrDobr.lnk'));
  if FileExists(ExpandConstant('{userprograms}\BobrDobr-VPN.lnk')) then
    DeleteFile(ExpandConstant('{userprograms}\BobrDobr-VPN.lnk'));

  LegacyGroupRu := ExpandConstant('{userprograms}\{#AppName}');
  LegacyGroupEn := ExpandConstant('{userprograms}\{#AppEnglishName}');
  if DirExists(LegacyGroupRu) then
    DelTree(LegacyGroupRu, True, True, True);
  if DirExists(LegacyGroupEn) then
    DelTree(LegacyGroupEn, True, True, True);

  // 4. Purge legacy HKCU registry keys so Windows doesn't show duplicate entries in Installed Apps
  PurgeAllBobrDobrRegistryKeysFromHive(HKCU);
  PurgeAllBobrDobrRegistryKeysFromHive(HKCU64);
end;

// Helper: Deletes Windows Defender Firewall rules for BobrDobr VPN daemons
procedure DeleteFirewallRules();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="BobrDobr AmneziaWG"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="BobrDobr-AmneziaWG"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="BobrDobr OpenConnect"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="BobrDobr-OpenConnect"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

// Helper: Cleans registry entries exhaustively across ALL hives (HKLM64, HKLM32, HKCU64, HKCU) on uninstallation
procedure CleanRegistryKeysOnUninstall();
begin
  PurgeAllBobrDobrRegistryKeysFromHive(HKLM64);
  PurgeAllBobrDobrRegistryKeysFromHive(HKLM32);
  PurgeAllBobrDobrRegistryKeysFromHive(HKCU64);
  PurgeAllBobrDobrRegistryKeysFromHive(HKCU);
end;

// Pre-installation initialization
function InitializeSetup(): Boolean;
var
  RetryChoice: Integer;
  AppMutexList: String;
begin
  Result := True;
  IsUpgradeMode := DetectExistingInstallation(PreviousVersion, PreviousInstallDir);

  AppMutexList := 'Global\BobrDobr_VPN_SingleInstance_Unified_v1,BobrDobr_VPN_SingleInstance_Unified_v1';

  // If another instance is running, offer to close it or close automatically in silent mode
  while CheckForMutexes(AppMutexList) do
  begin
    if WizardSilent then
    begin
      TerminateRunningInstances();
      Break;
    end;

    RetryChoice := MsgBox(CustomMessage('CloseRunningAppPrompt'), mbConfirmation, MB_YESNO);
    if RetryChoice = IDYES then
    begin
      TerminateRunningInstances();
    end
    else
    begin
      Result := False;
      Exit;
    end;
  end;
end;

// Adjust wizard UI for upgrade mode
procedure InitializeWizard();
var
  UpgradeMsg: String;
begin
  // Ensure installer window appears on top of all windows
  MakeWizardTopMost();

  if IsUpgradeMode then
  begin
    if PreviousVersion = '' then
      PreviousVersion := '1.1.x';

    UpgradeMsg := FmtMessage(CustomMessage('UpgradeDetected'), [PreviousVersion]);
    WizardForm.WelcomeLabel2.Caption := UpgradeMsg;

    // Preserve original installation directory ONLY if it is a valid directory
    // and NOT a legacy user-level AppData folder!
    if (PreviousInstallDir <> '') and DirExists(PreviousInstallDir) then
    begin
      if (Pos(LowerCase(ExpandConstant('{localappdata}')), LowerCase(PreviousInstallDir)) = 0) and
         (Pos(LowerCase(ExpandConstant('{userappdata}')), LowerCase(PreviousInstallDir)) = 0) then
      begin
        WizardForm.DirEdit.Text := PreviousInstallDir;
      end;
    end;
  end;
end;

// Re-assert topmost and foreground on wizard page changes to prevent UAC/Explorer from burying the window
procedure CurPageChanged(CurPageID: Integer);
begin
  MakeWizardTopMost();
end;

// Setup installation step notifications
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    // Proactively purge any legacy user-level installation and shortcuts before copying files
    PurgeLegacyUserInstallation();
  end;
end;

// Single-instance check before uninstallation
function InitializeUninstall(): Boolean;
var
  RetryChoice: Integer;
begin
  Result := True;
  while CheckForMutexes('Global\BobrDobr_VPN_SingleInstance_Unified_v1,BobrDobr_VPN_SingleInstance_Unified_v1') do
  begin
    RetryChoice := MsgBox(CustomMessage('AppRunningUninstall'), mbError, MB_RETRYCANCEL);
    if RetryChoice = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

// Step notifications during uninstallation
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDataDir: String;
  LocalAppDataDir: String;
  LegacyProgramsDir: String;
  AppDataDirVPN: String;
  LocalAppDataDirVPN: String;
  CommonAppDataDir: String;
  PromptMsg: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Terminate any running instances and VPN background daemons before files are deleted
    TerminateRunningInstances();
    // Delete Windows Firewall rules
    DeleteFirewallRules();
  end
  else if CurUninstallStep = usPostUninstall then
  begin
    // Clean all registry entries in both HKLM and HKCU
    CleanRegistryKeysOnUninstall();

    // AppData / Local directories cleanup prompt
    AppDataDir := ExpandConstant('{userappdata}\BobrDobr');
    LocalAppDataDir := ExpandConstant('{localappdata}\BobrDobr');
    LegacyProgramsDir := ExpandConstant('{localappdata}\Programs\BobrDobr');
    AppDataDirVPN := ExpandConstant('{userappdata}\BobrDobrVPN');
    LocalAppDataDirVPN := ExpandConstant('{localappdata}\BobrDobrVPN');
    CommonAppDataDir := ExpandConstant('{commonappdata}\BobrDobr');

    if DirExists(AppDataDir) or DirExists(LocalAppDataDir) or DirExists(LegacyProgramsDir) or
       DirExists(AppDataDirVPN) or DirExists(LocalAppDataDirVPN) or DirExists(CommonAppDataDir) then
    begin
      PromptMsg := FmtMessage(CustomMessage('CleanAppDataPrompt'), [AppDataDir]);
      if MsgBox(PromptMsg, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        if DirExists(AppDataDir) then
          DelTree(AppDataDir, True, True, True);
        if DirExists(LocalAppDataDir) then
          DelTree(LocalAppDataDir, True, True, True);
        if DirExists(LegacyProgramsDir) then
          DelTree(LegacyProgramsDir, True, True, True);
        if DirExists(AppDataDirVPN) then
          DelTree(AppDataDirVPN, True, True, True);
        if DirExists(LocalAppDataDirVPN) then
          DelTree(LocalAppDataDirVPN, True, True, True);
        if DirExists(CommonAppDataDir) then
          DelTree(CommonAppDataDir, True, True, True);
      end;
    end;
  end;
end;
