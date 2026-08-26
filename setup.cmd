@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1"
if errorlevel 1 (
  echo.
  echo Setup failed. Read docs\USER_GUIDE.md or run scripts\diagnose.ps1.
  pause
  exit /b 1
)
echo.
echo LocalFace Studio environment is ready. Models are installed separately.
pause
