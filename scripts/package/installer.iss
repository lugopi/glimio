#ifndef AppVersion
  #error "AppVersion must be supplied as /DAppVersion=0.4.2"
#endif
#ifndef Edition
  #error "Edition must be supplied as /DEdition=cli|web|web-diarization"
#endif
#ifndef PayloadDir
  #error "PayloadDir must point to the prepared payload folder"
#endif

#if Edition == "cli"
  #define ProductName "Glimio CLI"
#elif Edition == "web"
  #define ProductName "Glimio Web"
#else
  #define ProductName "Glimio Web avec diarisation"
#endif

[Setup]
AppId=Glimio-{#Edition}
AppName={#ProductName}
AppVersion={#AppVersion}
AppPublisher=Glimio
DefaultDirName={localappdata}\Programs\Glimio\{#Edition}
DefaultGroupName={#ProductName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes
OutputDir=..\..\dist\release\{#Edition}
OutputBaseFilename=Glimio-{#Edition}-{#AppVersion}-Windows-x64-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
#if Edition == "cli"
UninstallDisplayIcon={app}\GlimioCLI\GlimioCLI.exe
#else
UninstallDisplayIcon={app}\GlimioWeb\GlimioWeb.exe
#endif

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"; Flags: unchecked

[Dirs]
Name: "{localappdata}\Glimio\Data"; Flags: uninsneveruninstall

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
#if Edition == "cli"
Name: "{autoprograms}\{#ProductName} — aide"; Filename: "{app}\GlimioCLI\GlimioCLI.exe"; Parameters: "--help"; WorkingDir: "{localappdata}\Glimio\Data"
#else
Name: "{autoprograms}\{#ProductName}"; Filename: "{app}\GlimioWeb\GlimioWeb.exe"; WorkingDir: "{localappdata}\Glimio\Data"
#endif
Name: "{autodesktop}\{#ProductName}"; Filename: "{app}\GlimioWeb\GlimioWeb.exe"; WorkingDir: "{localappdata}\Glimio\Data"; Tasks: desktopicon; Check: IsWebEdition

[Code]
function IsWebEdition(): Boolean;
begin
  Result := '{#Edition}' <> 'cli';
end;
