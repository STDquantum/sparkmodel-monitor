@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
set "PYTHONUTF8=1"
if /i "%~1"=="browse" goto browse
if /i "%~1"=="manage" goto manage
if /i "%~1"=="refresh" goto refresh
echo 请使用根目录中的中文启动文件。
exit /b 1

:browse
echo 浏览目录：关闭此窗口可停止本地服务。
call :python scripts\serve_local.py --page index.html
goto finished

:manage
echo 管理商品与时间：关闭此窗口可停止本地服务。
call :python scripts\serve_local.py --page both
goto finished

:refresh
set "CARMODEL_ENABLED=true"
call :python scripts\refresh_carmodel.py --build
if errorlevel 1 goto finished
echo.
echo 比美高本地刷新完成。刷新目录页即可查看。
echo 如需同步线上，请提交并推送 data 和 docs 中的更新。

:finished
set "TASK_EXIT=%errorlevel%"
if not "%TASK_EXIT%"=="0" echo 执行失败，请检查上面的错误信息。
pause
exit /b %TASK_EXIT%

:python
if defined PYTHON_HOME (
    "%PYTHON_HOME%\python.exe" %*
) else if exist "D:\conda\env3.10\python.exe" (
    "D:\conda\env3.10\python.exe" %*
) else (
    py -3 %*
)
exit /b %errorlevel%
