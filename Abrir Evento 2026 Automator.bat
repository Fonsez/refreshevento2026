@echo off
setlocal
cd /d "%~dp0"

set "EXE_PATH=dist\Evento2026Automator\Evento2026Automator.exe"
if exist "%EXE_PATH%" (
    start "" "%EXE_PATH%"
    exit /b 0
)

set "PYTHON_CMD="
where py >nul 2>nul
if %errorlevel%==0 set "PYTHON_CMD=py"
if not defined PYTHON_CMD (
    where python >nul 2>nul
    if %errorlevel%==0 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo.
    echo Python nao foi encontrado no PC.
    echo.
    echo Para usar sem instalar Python, baixe a versao pronta em Releases.
    echo Para usar pelo codigo-fonte, instale Python 3.11+ e rode este arquivo de novo.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\pythonw.exe" (
    echo.
    echo Preparando o app pela primeira vez...
    echo Isso pode demorar alguns minutos.
    echo.
    %PYTHON_CMD% -m venv .venv || goto :fail
    call ".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :fail
    call ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
)

start "" ".venv\Scripts\pythonw.exe" "main.py"
exit /b 0

:fail
echo.
echo Nao foi possivel preparar o ambiente automaticamente.
echo Tente rodar de novo ou gere a versao .exe com build_exe.bat
echo.
pause
exit /b 1
