@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if defined PYTHON_HOME (
  "%PYTHON_HOME%\python.exe" history\server.py
) else if exist "D:\conda\env3.10\python.exe" (
  "D:\conda\env3.10\python.exe" history\server.py
) else (
  py -3 history\server.py
)
if errorlevel 1 echo Startup failed. Please install Git and Python 3.9 or later.
pause
