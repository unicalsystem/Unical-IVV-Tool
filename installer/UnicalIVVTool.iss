; Inno Setup script - Unical DO-178 IV&V Review Tool
; Produces ONE self-contained setup .exe (Python, Qt and all libraries inside).
#define AppName "Unical DO-178 IV&V Review Tool"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppExe "UnicalIVVTool.exe"

[Setup]
AppId={{7C3B2E54-5D1A-4F2E-9C61-0A7B3D9E4F21}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Unical Systems
AppPublisherURL=https://www.unical.in
AppSupportURL=https://www.unical.in
AppCopyright=Copyright (C) 2026 Unical Systems
DefaultDirName={autopf}\Unical Systems\IVV Review Tool
DefaultGroupName=Unical Systems
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\Output
OutputBaseFilename=UnicalIVVTool_Setup_{#AppVersion}
SetupIconFile=..\assets\unical.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
VersionInfoCompany=Unical Systems
VersionInfoDescription={#AppName} Setup
VersionInfoVersion={#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\UnicalIVVTool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Messages]
FinishedLabel=Setup has installed [name] on your computer.%n%nLogin: admin / admin@123 (prototype account).%nYour reviews, reports and logs are kept in:%n%LOCALAPPDATA%\Unical Systems\IVV Review Tool%nand are not removed on uninstall.
