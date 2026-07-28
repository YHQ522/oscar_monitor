; 管控平台客户端 - Inno Setup 安装脚本

[Setup]
AppName=管控平台客户端
AppVersion=1.0
DefaultDirName={pf}\OscarMonitorClient
DefaultGroupName=管控平台客户端
OutputDir=.\dist
OutputBaseFilename=OscarMonitor_Client_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=管控平台客户端
PrivilegesRequired=admin

[Messages]
SetupAppTitle=管控平台客户端 安装向导
SetupWindowTitle=管控平台客户端 安装
WelcomeLabel1=欢迎安装 [name]
WelcomeLabel2=即将安装 [name] 到您的计算机。%n%n此版本为纯客户端，需连接远程服务端。
WizardSelectDir=选择安装目录
SelectDirDesc=请选择 [name] 的安装目录。
SelectDirLabel3=安装程序将把 [name] 安装到以下目录。
SelectDirBrowseLabel=点击"浏览"选择其他文件夹。
SelectTasksDesc=请选择要执行的附加任务:
ReadyLabel1=安装程序已就绪。
ReadyLabel2a=点击"安装"开始安装。
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonFinish=完成(&F)
ButtonBack=< 上一步(&B)
FinishedLabel=[name] 安装完成。
FinishedHeadingLabel=[name] 安装完成。
ClickFinish=安装完成。
BeveledLabel=管控平台客户端 v1.0
WizardPreparing=正在准备安装...
WizardInstalling=正在安装 [name]，请稍候...
WizardSelectDir=选择安装目录
SelectDirBrowseLabel=浏览...

[CustomMessages]
CreateDesktopIcon=创建桌面快捷方式(&D)
SetServerPrompt=请输入远程服务端地址:

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "快捷方式:"

[Files]
Source: "dist\oscar-client.exe"; DestDir: "{app}"; DestName: "oscar-client.exe"; Flags: ignoreversion

[Dirs]
Name: "{app}\data"

[Code]
var
  ServerPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  ServerPage := CreateInputQueryPage(wpSelectDir,
    '服务端配置', '请输入远程服务端地址',
    '输入管控平台服务端的完整地址，例如 http://192.168.1.100:5080');
  ServerPage.Add('服务端地址:', False);
  ServerPage.Values[0] := 'http://';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ServerPage.ID then
    if (ServerPage.Values[0] = '') or (ServerPage.Values[0] = 'http://') then
    begin
      MsgBox('请输入服务端地址', mbError, MB_OK);
      Result := False;
    end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ServerURL: String;
begin
  if CurStep = ssPostInstall then
  begin
    ServerURL := ServerPage.Values[0];
    SaveStringToFile(ExpandConstant('{app}\server_url.txt'), ServerURL, False);
    CreateShellLink(ExpandConstant('{group}\管控平台客户端.lnk'), '管控平台客户端',
      ExpandConstant('{app}\oscar-client.exe'), '--server ' + ServerURL,
      ExpandConstant('{app}'), '', 0, SW_SHOWNORMAL);
    if IsTaskSelected('desktopicon') then
      CreateShellLink(ExpandConstant('{autodesktop}\管控平台客户端.lnk'), '管控平台客户端',
        ExpandConstant('{app}\oscar-client.exe'), '--server ' + ServerURL,
        ExpandConstant('{app}'), '', 0, SW_SHOWNORMAL);
  end;
end;
