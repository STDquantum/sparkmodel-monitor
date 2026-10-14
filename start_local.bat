@echo off
setlocal
cd /d "%~dp0"
if defined PYTHON_HOME (
    "%PYTHON_HOME%\python.exe" serve_local.py --page both
) else if exist "D:\conda\env3.10\python.exe" (
    "D:\conda\env3.10\python.exe" serve_local.py --page both
) else (
    py -3 serve_local.py --page both
)
pause
