@echo off
setlocal
cd /d "%~dp0"
set "CARMODEL_ENABLED=true"
set "PYTHONUTF8=1"
if defined PYTHON_HOME (
    "%PYTHON_HOME%\python.exe" refresh_carmodel.py --build
) else if exist "D:\conda\env3.10\python.exe" (
    "D:\conda\env3.10\python.exe" refresh_carmodel.py --build
) else (
    py -3 refresh_carmodel.py --build
)
if errorlevel 1 (
    echo.
    echo Refresh failed. Please check the error above before retrying.
) else (
    echo.
    echo Burago catalogue and images refreshed locally.
    echo To publish online, commit and push state.json, carmodel-coverage.json and docs.
)
pause
