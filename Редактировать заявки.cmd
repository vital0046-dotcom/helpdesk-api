@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo First run start.ps1 to install the project environment.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m tools.helpdesk_editor
