; BlemmLauncher release installer
#define AppVersion GetEnv("BLEMM_VERSION")

[Setup]
AppName=BlemmLauncher
AppVersion={#AppVersion}
WizardStyle=modern
DefaultDirName={autopf}\BlemmLauncher
DefaultGroupName=BlemmLauncher
Compression=lzma2/max
SolidCompression=yes
OutputBaseFilename=BlemmLauncher-{#AppVersion}-Setup
PrivilegesRequired=admin
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\BlemmLauncher.exe

[Files]
Source: "dist\BlemmLauncher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\BlemmLauncher"; Filename: "{app}\BlemmLauncher.exe"; IconFilename: "{app}\app_icon.ico"
Name: "{autodesktop}\BlemmLauncher"; Filename: "{app}\BlemmLauncher.exe"; IconFilename: "{app}\app_icon.ico"

[Run]
Filename: "{app}\BlemmLauncher.exe"; Description: "Launch BlemmLauncher"; Flags: nowait postinstall skipifsilent
