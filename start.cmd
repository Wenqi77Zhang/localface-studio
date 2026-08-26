@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. Run scripts\diagnose.ps1 for a component-by-component report.
  pause
  exit /b 1
)
