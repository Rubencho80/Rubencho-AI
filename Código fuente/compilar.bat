@echo off
setlocal EnableExtensions
title Compilar Rubencho AI
cd /d "%~dp0"

rem ======================================================================
rem  Compila Rubencho AI como aplicacion de Windows y crea su instalador:
rem    1) PyInstaller  ->  _compilacion\dist\Rubencho AI\Rubencho AI.exe
rem    2) Inno Setup   ->  ..\Instalar Rubencho AI.exe
rem  Uso:  compilar.bat  [ruta\python.exe]
rem ======================================================================

set "PY=%~1"
if defined PY goto :tengo_python
set "PY_STORE=%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
if exist "%PY_STORE%" set "PY=%PY_STORE%"
if not defined PY for /f "delims=" %%p in ('py -3.13 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%p"
if not defined PY for /f "delims=" %%p in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%p"
if not defined PY (
    echo [ERROR] No se ha encontrado Python.
    goto :error
)
:tengo_python
echo Python: %PY%
"%PY%" -c "import PyInstaller, faster_whisper, pystray" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] A ese Python le faltan librerias. Instalalas con:
    echo    "%PY%" -m pip install -r requirements.txt pyinstaller
    goto :error
)

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo [ERROR] Falta Inno Setup 6. Instalalo con:  winget install JRSoftware.InnoSetup
    goto :error
)

rem Librerias del puente de WhatsApp (van dentro del instalador)
if not exist "whatsapp\node_modules\@whiskeysockets\baileys" (
    echo Instalando las librerias de WhatsApp con npm...
    pushd whatsapp
    call npm ci --omit=dev
    if errorlevel 1 (
        popd
        echo [ERROR] Falta Node.js o ha fallado npm. Instala Node.js 18 o superior.
        goto :error
    )
    popd
)

set "OUT=%~dp0_compilacion"
echo.
echo [1/2] Compilando la aplicacion con PyInstaller (unos minutos)...
"%PY%" -m PyInstaller "Rubencho AI.spec" --noconfirm --clean --log-level WARN --workpath "%OUT%\work" --distpath "%OUT%\dist"
if errorlevel 1 goto :error
if not exist "%OUT%\dist\Rubencho AI\Rubencho AI.exe" goto :error

echo.
echo [2/2] Creando el instalador con Inno Setup...
"%ISCC%" /Q "/DDistDir=%OUT%\dist\Rubencho AI" "/DOutDir=%~dp0.." instalador.iss
if errorlevel 1 goto :error

echo.
echo ============================================================
echo   Listo:  "%~dp0..\Instalar Rubencho AI.exe"
echo ============================================================
rem Los ficheros intermedios ocupan mucho: se borran
rmdir /s /q "%OUT%" 2>nul
if not defined RUBENCHO_NOPAUSE pause
endlocal
exit /b 0

:error
echo.
echo La compilacion ha fallado. Revisa los mensajes de arriba.
if not defined RUBENCHO_NOPAUSE pause
endlocal
exit /b 1
