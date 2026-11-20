@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONPYCACHEPREFIX=%~dp0interni\pycache"
set "TEMP=%~dp0interni\docasne"
set "TMP=%~dp0interni\docasne"
if not exist "%TEMP%" mkdir "%TEMP%"

set "PYTHON_CMD="
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_CMD=%~dp0.venv\Scripts\python.exe"
if defined PYTHON_CMD goto spustit
where py >nul 2>nul
if %errorlevel%==0 set "PYTHON_CMD=py -3"
if defined PYTHON_CMD goto spustit
where python >nul 2>nul
if %errorlevel%==0 set "PYTHON_CMD=python"
if defined PYTHON_CMD goto spustit

echo Python 3 nebyl nalezen. Nainstalujte Python 3.10 nebo novější a spusťte instalovat.py.
set "NAVRAT=1"
goto konec

:spustit
%PYTHON_CMD% -B "%~dp0skript\cms.py"
set "NAVRAT=%errorlevel%"

:konec
echo.
pause
endlocal & exit /b %NAVRAT%
