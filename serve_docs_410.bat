@echo off
REM 启动本地 HTTP 服务器，服务 docs 目录，监听 localhost:410
setlocal
if defined PYTHON_HOME (
    "%PYTHON_HOME%\python" "%~dp0serve_local.py"
) else (
    "D:\conda\env3.10\python.exe" "%~dp0serve_local.py"
)
endlocal
