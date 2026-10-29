#define AppVersion "2.1.1"

[Setup]
AppId={{56B3C7A4-6F9E-4F8B-98F1-CC0C9F392E41}
AppName=J.A.R.V.I.S. CE-21
AppVersion={#AppVersion}
AppVerName=J.A.R.V.I.S. CE-21 v{#AppVersion}
AppPublisher=MEHNATKASH GROUP
DefaultDirName={localappdata}\Programs\JARVIS
DefaultGroupName=J.A.R.V.I.S. CE-21
UninstallDisplayName=J.A.R.V.I.S. CE-21 v{#AppVersion}
UninstallDisplayIcon={app}\JARVIS.exe
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
Compression=lzma2/fast
SolidCompression=yes
SetupIconFile=..\assets\JARVIS.ico
OutputDir=..\dist
OutputBaseFilename=JARVIS-Setup-2.1.1
VersionInfoVersion=2.1.1.0
VersionInfoCompany=MEHNATKASH GROUP
VersionInfoDescription=J.A.R.V.I.S. CE-21 (v2.1.1) Windows Installer
VersionInfoProductName=J.A.R.V.I.S. CE-21
VersionInfoProductVersion=2.1.1

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut (Ish stolida yorliq yaratish)"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\JARVIS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\J.A.R.V.I.S. CE-21"; Filename: "{app}\JARVIS.exe"; IconFilename: "{app}\_internal\assets\JARVIS.ico"; WorkingDir: "{app}"
Name: "{autodesktop}\J.A.R.V.I.S. CE-21"; Filename: "{app}\JARVIS.exe"; IconFilename: "{app}\_internal\assets\JARVIS.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\JARVIS.exe"; Description: "Launch J.A.R.V.I.S. CE-21 v2.1.1"; Flags: postinstall nowait skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
	if CurUninstallStep = usUninstall then
		RegDeleteValue(HKEY_CURRENT_USER,
			'Software\Microsoft\Windows\CurrentVersion\Run', 'JARVIS');
end;
