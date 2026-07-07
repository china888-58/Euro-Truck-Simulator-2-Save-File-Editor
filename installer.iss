; EuroTruckSaveEditor Inno Setup 安装脚本
; 用法: ISCC.exe installer.iss
; 输出: dist\EuroTruckSaveEditor-Setup-v3.0.1.exe

#define MyAppName "欧卡 / 美卡 存档编辑器"
#define MyAppNameEN "EuroTruckSaveEditor"
#define MyAppGroupName "欧卡存档编辑器"
#define MyAppVersion "3.0.1"
#define MyAppPublisher "Eurocard-Tools"
#define MyAppURL "https://github.com/china888-58/Euro-Truck-Simulator-2-Save-File-Editor"
#define MyAppExeName "EuroTruckSaveEditor.exe"

[Setup]
AppId={{B8F3A2E7-1C5D-4E8A-9F2B-3A6C7D8E9F01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppNameEN}
DefaultGroupName={#MyAppGroupName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=EuroTruckSaveEditor-Setup-v{#MyAppVersion}
SetupIconFile=app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
; CloseApplications=yes: 使用 Windows Restart Manager 自动关闭占用文件的进程
; CloseApplicationsFilter: 只匹配我们自己的 EXE(之前写 *.exe 会匹配安装包自身,导致 Restart Manager 误判)
; RestartApplications=no: 不自动重启被关闭的进程(我们自己启动新版本)
CloseApplications=yes
RestartApplications=no
CloseApplicationsFilter={#MyAppExeName}
; AppMutex 已移除: 自更新批处理脚本已杀进程,AppMutex 在此场景下会导致安装程序静默退出
; PrepareToInstall 函数已处理"文件被占用"的情况(杀进程 + 重试 20 次)
; AppMutex=Global\EuroTruckSaveEditor_Running

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; onedir 打包结果:dist\EuroTruckSaveEditor\
Source: "dist\EuroTruckSaveEditor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppGroupName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppGroupName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppGroupName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; 卸载时关闭运行中的程序(杀进程树)
Filename: "{cmd}"; Parameters: "/c taskkill /F /T /IM {#MyAppExeName} 2>nul"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// ===== Windows API 声明 =====
const
  GENERIC_WRITE = $40000000;
  OPEN_EXISTING = 3;
  INVALID_HANDLE_VALUE = -1;

function CreateFile(lpFileName: String; dwDesiredAccess: LongWord; dwShareMode: LongWord;
  lpSecurityAttributes: Integer; dwCreationDisposition: LongWord; dwFlagsAndAttributes: LongWord;
  hTemplateFile: THandle): THandle;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseHandle(hObject: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

// ===== 工具函数 =====

// 强制杀掉所有 EuroTruckSaveEditor.exe 进程(包括子进程树)
procedure KillAppProcesses();
var
  resultCode: Integer;
begin
  Exec(ExpandConstant('{cmd}'), '/c taskkill /F /T /IM {#MyAppExeName} 2>nul', '', SW_HIDE, ewWaitUntilTerminated, resultCode);
end;

// 检测 EXE 文件是否可写(以独占写模式打开文件,成功=可写=无进程占用)
function IsExeWritable(exePath: String): Boolean;
var
  hFile: THandle;
begin
  Result := False;
  if not FileExists(exePath) then begin
    Result := True;
    Exit;
  end;
  // dwShareMode=0 表示独占模式(不允许其他进程读写)
  // 如果文件被其他进程占用,CreateFile 返回 INVALID_HANDLE_VALUE
  hFile := CreateFile(exePath, GENERIC_WRITE, 0, 0, OPEN_EXISTING, $80, 0);
  if hFile <> INVALID_HANDLE_VALUE then begin
    Result := True;
    CloseHandle(hFile);
  end;
end;

// ===== InitializeSetup: 安装入口 =====
function InitializeSetup(): Boolean;
var
  uninstallCmd: String;
  resultCode: Integer;
begin
  Result := True;

  // 第 1 步:强制杀进程(包括子进程树)
  KillAppProcesses();
  Sleep(800);

  // 第 2 步:静默卸载旧版本(如果存在)
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1', 'UninstallString', uninstallCmd) or
     RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1', 'UninstallString', uninstallCmd) then
  begin
    Exec(RemoveQuotes(uninstallCmd), '/SILENT /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, resultCode);
  end;
end;

// ===== PrepareToInstall: 文件安装前最终检查 =====
// 在 Inno Setup 开始复制/替换文件之前反复杀进程并验证 EXE 文件可写
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  exePath: String;
  maxAttempts: Integer;
  attempt: Integer;
begin
  Result := '';
  exePath := ExpandConstant('{app}\{#MyAppExeName}');
  maxAttempts := 20;

  for attempt := 1 to maxAttempts do begin
    KillAppProcesses();
    Sleep(300);
    if IsExeWritable(exePath) then begin
      Exit;
    end;
    Sleep(200);
  end;

  // 20 次重试后仍被占用,返回空让安装继续
  // Inno Setup 的 CloseApplications + Restart Manager 会做最后尝试
  Result := '';
end;
