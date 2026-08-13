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
ClickFinish=安装完成。程序启动后请使用浏览器访问（默认账号 admin / admin123，请及时修改）。
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
Name: "autostart"; Description: "{cm:AutoStart}"; GroupDescription: "附加功能:"

[Files]
; 单文件可执行程序（已内嵌后端 + 前端产物，免 Python/Node）
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; 数据目录（安装到 ProgramData，运行时可写，所有用户共享）
Name: "{commonappdata}\OscarMonitor\data"

; 让程序把数据写到可写目录（Program Files 安装位置运行时不具备写权限）
; 通过系统环境变量 OSCAR_DATA_DIR 注入（pydantic-settings 前缀 OSCAR_）
[Registry]
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "OSCAR_DATA_DIR"; ValueData: "{commonappdata}\OscarMonitor\data"; Flags: uninsdeletevalue

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent shellexec

[Registry]
; 可选：开机自动启动（当前用户）
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "OscarMonitor"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[UninstallDelete]
Type: dirifempty; Name: "{commonappdata}\OscarMonitor\data"
Type: dirifempty; Name: "{commonappdata}\OscarMonitor"
Type: dirifempty; Name: "{app}"

[Code]
var
  PortPage: TInputQueryWizardPage;

// 安装前/卸载时结束正在运行的进程，避免文件占用
procedure KillRunningApp();
var
  ResultCode: Integer;
begin
  Exec('taskkill', '/f /im oscar-monitor.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
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

// 安装完成后，若尚无配置文件则写入初始端口（升级安装保留已有配置）
procedure WritePortConfig();
var
  CfgPath, PortStr: String;
begin
  CfgPath := ExpandConstant('{commonappdata}\OscarMonitor\data\config.json');
  if FileExists(CfgPath) then
    Exit;
  ForceDirectories(ExpandConstant('{commonappdata}\OscarMonitor\data'));
  PortStr := Trim(PortPage.Values[0]);
  if PortStr = '' then
    PortStr := '5080';
  SaveStringToFile(CfgPath, '{"port": ' + PortStr + '}', False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    KillRunningApp();
  if CurStep = ssPostInstall then
    WritePortConfig();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    KillRunningApp();
end;
