@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\verify_install.ps1"
if errorlevel 1 (
  echo.
  echo Installation verification failed. Read runtime\diagnostics\localface-diagnostics.json.
  pause
  exit /b 1
)
echo.
echo Automated installation verification passed.
echo A real authorized face swap and visual inspection are still required for final acceptance.
pause
