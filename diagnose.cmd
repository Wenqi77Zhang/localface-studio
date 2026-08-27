@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\diagnose.ps1" -ExportReport
echo.
echo A privacy-safe report was written to runtime\diagnostics\localface-diagnostics.json.
echo It does not contain images, face data, task identifiers, username, hostname, or local paths.
pause
