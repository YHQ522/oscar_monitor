; ============================================================
;  oscar-monitor 数据库监控管控平台 - Windows 安装包脚本
;  Inno Setup 6（>= 6.3，使用 [Environment] 章节）
;  编译: iscc setup.iss   （或运行 build_win.bat 一键打包）
;  产物: build\dist\oscar-monitor-setup-2.0.0.exe
; ============================================================

#define MyAppName "oscar-monitor 数据库监控管控平台"
#define MyAppVersion "2.0.0"
#define MyAppExeName "oscar-monitor.exe"
#define MyAppPublisher "oscar-monitor"
#define MyAppURL "http://localhost:5080"
#define MyAppId "A1B2C3D4-5E6F-4A7B-8C9D-0E1F2A3B4C5D"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppComments=基于 SSH/CLI 的多数据库（Oscar/MySQL/PostgreSQL/Oracle）监控管控平台
DefaultDirName={autopf}\OscarMonitor
DefaultGroupName=oscar-monitor
DisableDirPage=no
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=oscar-monitor-setup-{#MyAppVersion}
SetupIconFile=assets\oscar-monitor.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ChangesEnvironment=yes
AppendDefaultDirName=no
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Messages]
SetupAppTitle=安装 {#MyAppName}
SetupWindowTitle=安装 - {#MyAppName}
WelcomeLabel1=欢迎安装 {#MyAppName}
WelcomeLabel2=本程序将把 {#MyAppName} 安装到您的计算机。%n%n建议关闭其他应用程序后再继续。
WizardSelectDir=选择安装位置
SelectDirDesc=请选择 {#MyAppName} 的安装目录。
SelectDirLabel3=安装程序将把 {#MyAppName} 安装到以下目录。%n点击"下一步"继续。
SelectDirBrowseLabel=点击"浏览"选择其他文件夹。
ReadyLabel1=安装程序已就绪。
ReadyLabel2a=点击"安装"开始安装，点击"上一步"检查或修改设置。
ReadyLabel2b=点击"安装"继续安装。
FinishedLabel={#MyAppName} 已安装完成。
FinishedHeadingLabel={#MyAppName} 安装完成。
ClickFinish=安装完成。服务已在后台运行（Windows 服务：oscar-monitor），请使用浏览器访问（默认账号 admin / admin123，请及时修改）。
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonFinish=完成(&F)
ButtonBack=< 上一步(&B)
ButtonCancel=取消
ButtonBrowse=浏览...
StatusExtractFiles=正在解压文件...
StatusCreateDirs=正在创建目录...
StatusCreateIcons=正在创建快捷方式...
StatusRegisterFiles=正在注册文件...
StatusRunProgram=正在启动程序...
UninstallStatusLabel=正在卸载，请稍候...
ConfirmUninstall=确定要完全卸载 {#MyAppName} 及其所有组件吗？
ExitSetupTitle=退出安装
ExitSetupMessage=安装尚未完成。确定退出安装程序吗？
AboutSetupMenuItem=关于安装程序...
AboutSetupTitle=关于安装程序
AboutSetupMessage={#MyAppName} 安装程序%n版本 {#MyAppVersion}
BeveledLabel={#MyAppName} v{#MyAppVersion}
DiskSpaceMBLabel=至少需要 [mb] MB 可用磁盘空间。
WizardPreparing=正在准备安装...
WizardInstalling=正在安装 {#MyAppName}，请稍候...
PrepareDesc=安装程序正在准备安装向导。请稍候。
ReadyMemoDir=安装目录:
ReadyMemoTasks=附加任务:
ReadyMemoUserInfo=安装信息:
InstallingLabel=正在复制文件，请稍候...
FinishedRestartLabel=安装完成。需要重新启动计算机。
FinishedNoIconsCheck=启动 {#MyAppName}
UninstalledAll={#MyAppName} 已完全卸载。
PrivilegesRequiredOverride=安装需要管理员权限。请以管理员身份运行。

[CustomMessages]
CreateDesktopIcon=创建桌面快捷方式(&D)
AutoStart=开机自动启动(&S)

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "快捷方式:"

[Files]
; 单文件可执行程序（已内嵌后端 + 前端产物，免 Python/Node）
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; NSSM（服务管理器）：按系统架构安装对应版本，用于注册后台 Windows 服务
Source: "nssm\win64\nssm.exe"; DestDir: "{app}\bin"; Flags: ignoreversion; Check: IsWin64
Source: "nssm\win32\nssm.exe"; DestDir: "{app}\bin"; Flags: ignoreversion; Check: "not IsWin64"

[Dirs]
; 数据目录（安装到 ProgramData，运行时可写，所有用户共享）
Name: "{commonappdata}\OscarMonitor\data"
; 服务日志目录（nssm AppStdout/AppStderr 输出）
Name: "{commonappdata}\OscarMonitor\logs"

; 让程序把数据写到可写目录（Program Files 安装位置运行时不具备写权限）
; 通过系统环境变量 OSCAR_DATA_DIR 注入（pydantic-settings 前缀 OSCAR_）
[Registry]
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "OSCAR_DATA_DIR"; ValueData: "{commonappdata}\OscarMonitor\data"; Flags: uninsdeletevalue

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon


[UninstallDelete]
Type: dirifempty; Name: "{commonappdata}\OscarMonitor\data"
Type: dirifempty; Name: "{commonappdata}\OscarMonitor"
Type: dirifempty; Name: "{app}"

[Code]
var
  PortPage: TInputQueryWizardPage;

const
  SvcName = 'oscar-monitor';

// 安装前/卸载时结束正在运行的进程，避免文件占用
procedure KillRunningApp();
var
  ResultCode: Integer;
begin
  Exec('taskkill', '/f /im oscar-monitor.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

// 调用 nssm（安装/升级期间 nssm 位于 {app}\bin）
procedure NssmRun(Params: String);
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{app}\bin\nssm.exe'), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

// 旧安装目录下的 nssm 路径（升级安装时用于停止旧服务）
function OldNssmPath(): String;
var
  OldDir: String;
begin
  Result := '';
  if RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1', 'InstallLocation', OldDir) then
    Result := OldDir + '\bin\nssm.exe';
end;

// 停止服务（升级安装覆盖文件前调用）：优先当前安装目录，回退旧目录，最后兜底杀进程
procedure StopService();
var
  Nssm: String;
  ResultCode: Integer;
begin
  Nssm := ExpandConstant('{app}\bin\nssm.exe');
  if not FileExists(Nssm) then
    Nssm := OldNssmPath();
  if Nssm <> '' then
    Exec(Nssm, 'stop ' + SvcName, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  KillRunningApp();
end;

// 注册为 Windows 后台服务（NSSM）：开机自启 + 崩溃自动重启 + 日志落盘
procedure InstallService();
var
  LogDir: String;
begin
  LogDir := ExpandConstant('{commonappdata}\OscarMonitor\logs');
  ForceDirectories(LogDir);
  // 幂等：先移除同名旧服务（不存在时报错，忽略）
  NssmRun('remove ' + SvcName + ' confirm');
  NssmRun('install ' + SvcName + ' "' + ExpandConstant('{app}\{#MyAppExeName}') + '"');
  NssmRun('set ' + SvcName + ' AppDirectory "' + ExpandConstant('{app}') + '"');
  NssmRun('set ' + SvcName + ' AppStdout "' + LogDir + '\out.log"');
  NssmRun('set ' + SvcName + ' AppStderr "' + LogDir + '\err.log"');
  NssmRun('set ' + SvcName + ' AppRotateFiles 1');
  NssmRun('set ' + SvcName + ' AppRotateBytes 10485760');
  // 数据目录通过服务环境变量注入，不依赖系统环境变量广播（首次安装免重启即生效）
  NssmRun('set ' + SvcName + ' AppEnvironmentExtra OSCAR_DATA_DIR=' + ExpandConstant('{commonappdata}\OscarMonitor\data'));
  NssmRun('set ' + SvcName + ' Start SERVICE_AUTO_START');
  NssmRun('start ' + SvcName);
end;

// 端口输入页（安装时指定端口；静默安装用 /Port=8080 传入）
procedure InitializeWizard();
begin
  PortPage := CreateInputQueryPage(
    wpSelectDir,
    '服务端口',
    '设置 Web 服务监听端口',
    '默认 5080。安装后也可在「系统配置」页或 config.json 中修改（重启生效）。');
  PortPage.Add('监听端口:', False);
  PortPage.Values[0] := ExpandConstant('{param:Port|5080}');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  P: Integer;
begin
  Result := True;
  if CurPageID = PortPage.ID then
  begin
    P := StrToIntDef(Trim(PortPage.Values[0]), 0);
    if (P < 1) or (P > 65535) then
    begin
      MsgBox('请输入 1-65535 之间的有效端口号。', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

// 安装完成后写入/更新监听端口。
// 全新安装：创建 {"port": X}；升级安装：用 PowerShell 仅更新 port 字段（保留其余配置）。
// 写入使用无 BOM 的 UTF-8，避免后端 json.load 因 BOM 解析失败。
procedure WritePortConfig();
var
  CfgPath, PortStr, PsCmd: String;
  ResultCode: Integer;
begin
  CfgPath := ExpandConstant('{commonappdata}\OscarMonitor\data\config.json');
  ForceDirectories(ExpandConstant('{commonappdata}\OscarMonitor\data'));
  PortStr := Trim(PortPage.Values[0]);
  if PortStr = '' then
    PortStr := '5080';
  PsCmd := '-NoProfile -ExecutionPolicy Bypass -Command "$c=@{port=' + PortStr + '};$p=''' + CfgPath + ''';if(Test-Path $p){$o=Get-Content -Raw $p|ConvertFrom-Json -ErrorAction SilentlyContinue;if($o){$o|Add-Member -Force -NotePropertyName port -NotePropertyValue ([int]' + PortStr + ');$c=$o}};[IO.File]::WriteAllText($p,($c|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))"';
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), PsCmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    StopService();
  if CurStep = ssPostInstall then
  begin
    WritePortConfig();
    InstallService();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    NssmRun('stop ' + SvcName);
    NssmRun('remove ' + SvcName + ' confirm');
    KillRunningApp();
  end;
end;
