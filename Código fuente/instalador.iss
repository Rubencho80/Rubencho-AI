; Instalador de Rubencho AI (Inno Setup 6).
; Lo compila compilar.bat, que le pasa:  /DDistDir=<carpeta de PyInstaller>  /DOutDir=<destino>

#define AppName  "Rubencho AI"
#define AppExe   "Rubencho AI.exe"
#define AppUMID  "RubenchoAI.Asistente"
; Versión interna: solo aparece en Propiedades → Detalles del instalador, nunca en el asistente
#define AppBuild "1.3.1"
#ifndef DistDir
  #define DistDir "_compilacion\dist\Rubencho AI"
#endif
#ifndef OutDir
  #define OutDir ".."
#endif

[Setup]
AppId={{8F3C2B7E-5D1A-4C9E-9B6F-2A7D4E1C3B90}
AppName={#AppName}
AppVerName={#AppName}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutDir}
OutputBaseFilename=Instalar Rubencho AI
SetupIconFile=recursos\rubencho.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile=recursos\instalador_lateral_1x.bmp,recursos\instalador_lateral_2x.bmp
WizardSmallImageFile=recursos\instalador_cabecera_1x.bmp,recursos\instalador_cabecera_2x.bmp
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4
; Si Rubencho AI (o una versión anterior) está abierto, pide cerrarlo antes de seguir
#ifndef SIN_MUTEX
AppMutex=RubenchoAI_InstanciaUnica
#endif
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no
VersionInfoVersion={#AppBuild}
VersionInfoProductName={#AppName}
VersionInfoDescription=Instalador de {#AppName}
VersionInfoCompany={#AppName}

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Messages]
es.WelcomeLabel2=Se instalará [name] en tu ordenador: tu asistente de voz con inteligencia artificial.%n%nSe recomienda cerrar las demás aplicaciones antes de continuar.
es.FinishedLabel=Rubencho AI se ha instalado. Lo encontrarás en el menú Inicio y, mientras esté abierto, en el icono junto al reloj.

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"
Name: "autostart"; Description: "Abrir Rubencho AI automáticamente al iniciar Windows"; GroupDescription: "Inicio:"
Name: "chromium"; Description: "Descargar el navegador para que la IA pueda usar páginas web (unos 150 MB)"; GroupDescription: "Opcional:"; Flags: unchecked

[InstallDelete]
; Al actualizar, se quitan las librerías de la versión anterior antes de copiar las nuevas
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "whatsapp\*"; DestDir: "{app}\whatsapp"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUMID}"; Comment: "Asistente de voz con inteligencia artificial"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUMID}"; Comment: "Asistente de voz con inteligencia artificial"; Tasks: desktopicon

[Registry]
; Inicio con Windows (la propia app lo mantiene después según su configuración)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"" --tray"; Tasks: autostart
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "{#AppName}"; Flags: uninsdeletevalue
; La versión anterior (script de Python) deja de arrancar sola
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "VoiceAI"; Flags: deletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--instalar-navegador"; StatusMsg: "Descargando el navegador para el control web…"; Tasks: chromium; Flags: runhidden waituntilterminated
Filename: "{app}\{#AppExe}"; Description: "Abrir Rubencho AI ahora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Cierra Rubencho AI (y el puente de WhatsApp) antes de desinstalar
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM ""{#AppExe}"""; Flags: runhidden; RunOnceId: "CerrarRubencho"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\whatsapp"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\Rubencho AI');
    if DirExists(DataDir) and not UninstallSilent then
      if MsgBox('¿Quieres borrar también tus datos de Rubencho AI?' + #13#10 +
                '(configuración, memoria, recordatorios, capturas, historial y sesión de WhatsApp)' + #13#10#13#10 +
                'Si vas a volver a instalarlo, elige «No» para conservarlos.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
