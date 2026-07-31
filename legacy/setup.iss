; 管控平台 - Inno Setup 安装脚本
; 运行: iscc setup.iss

[Setup]
AppName=管控平台
AppVersion=1.0
DefaultDirName={pf}\OscarMonitor
DefaultGroupName=管控平台
OutputDir=.\dist
OutputBaseFilename=OscarMonitor_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=管控平台
PrivilegesRequired=admin

[Messages]
SetupAppTitle=管控平台 安装向导
SetupWindowTitle=管控平台 安装
WelcomeLabel1=欢迎安装 [name]
WelcomeLabel2=即将安装 [name/ver] 到您的计算机。%n%n建议关闭其他应用程序后再继续。
WizardSelectDir=选择安装目录
SelectDirDesc=请选择 [name] 的安装目录。
SelectDirLabel3=安装程序将把 [name] 安装到以下目录。
SelectDirBrowseLabel=点击"浏览"选择其他文件夹。
SelectTasksDesc=请选择要执行的附加任务:
ReadyLabel1=安装程序已就绪。
ReadyLabel2a=点击"安装"开始安装，点击"上一步"修改设置。
ReadyLabel2b=点击"安装"继续。
FinishedLabel=[name] 安装完成。
FinishedHeadingLabel=[name] 安装完成。
ClickFinish=安装完成。访问 http://localhost:5080 开始使用。
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
UninstallStatusLabel=正在准备卸载，请稍候...
ConfirmUninstall=确定要完全卸载 [name] 及其所有组件吗？
ExitSetupTitle=退出安装
ExitSetupMessage=安装尚未完成。确定退出安装程序吗？
AboutSetupMenuItem=关于安装程序...
AboutSetupTitle=关于安装程序
AboutSetupMessage=管控平台 Windows 安装程序%n版本 1.0
BeveledLabel=管控平台 v1.0
DiskSpaceMBLabel=至少需要 [mb] MB 可用磁盘空间。
WizardPreparing=正在准备安装...
WizardInstalling=正在安装 [name]，请稍候...
PrepareDesc=安装程序正在准备安装向导。请稍候。
SelectStartMenuFolderDesc=请选择安装程序创建快捷方式的开始菜单文件夹。
SelectStartMenuFolderBrowseLabel=浏览开始菜单文件夹:
SelectProgramGroupDesc=请选择 [name] 的开始菜单文件夹。
ReadyMemoUserInfo=安装位置:
ReadyMemoDir=安装目录:
ReadyMemoTasks=附加任务:
ReadyMemoGroup=开始菜单文件夹:
InstallingLabel=正在复制文件，请稍候...
FinishedRestartLabel=安装完成。需要重新启动计算机。
FinishedNoIconsCheck=启动 [name]
UninstalledMost=[name] 已部分卸载。
UninstalledAll=[name] 已完全卸载。
PrivilegesRequiredOverride=安装需要管理员权限。请以管理员身份运行。
NoUninstallWarning=建议关闭其他应用程序后再继续卸载。

[CustomMessages]
CreateDesktopIcon=创建桌面快捷方式(&D)
AutoStart=开机自动启动(&S)

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "快捷方式:"
Name: "autostart"; Description: "{cm:AutoStart}"; GroupDescription: "附加功能:"

[Files]
Source: "dist\oscar-monitor.exe"; DestDir: "{app}"; DestName: "oscar-monitor.exe"; Flags: ignoreversion
Source: "static\*"; DestDir: "{app}\static"; Flags: ignoreversion recursesubdirs
Source: "templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\管控平台"; Filename: "{app}\oscar-monitor.exe"; WorkingDir: "{app}"
Name: "{group}\卸载管控平台"; Filename: "{uninstallexe}"
Name: "{autodesktop}\管控平台"; Filename: "{app}\oscar-monitor.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\oscar-monitor.exe"; Description: "启动管控平台"; Flags: nowait postinstall skipifsilent shellexec

[Registry]
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "OscarMonitor"; ValueData: "{app}\oscar-monitor.exe"; Flags: uninsdeletevalue; Tasks: autostart

[UninstallRun]
Filename: "taskkill"; Parameters: "/f /im oscar-monitor.exe"; Flags: runhidden

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
end;
