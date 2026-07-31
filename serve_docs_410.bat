@echo off
REM 启动本地 HTTP 服务器，服务 docs 目录，监听 localhost:410
setlocal
if defined PYTHON_HOME (
    "%PYTHON_HOME%\python" -m http.server 410 --bind 127.0.0.1 --directory docs
) else (
    python -m http.server 410 --bind 127.0.0.1 --directory docs
)
endlocal
