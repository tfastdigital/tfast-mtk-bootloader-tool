@echo off
setlocal EnableExtensions
title TFast MTK Bootloader Tool (CLI Edition v2.0.0)
cd /d "%~dp0"

set "PYCMD="
if exist "%APPDATA%\uv\python\cpython-3.14-windows-x86_64-none\python.exe" (
    set "PYCMD=%APPDATA%\uv\python\cpython-3.14-windows-x86_64-none\python.exe"
)
if not defined PYCMD (
    for /d %%D in ("%APPDATA%\uv\python\cpython-3.14*") do (
        if exist "%%~fD\python.exe" set "PYCMD=%%~fD\python.exe"
    )
)
if not defined PYCMD (
    py -3 -c "import sys" >nul 2>&1 && set "PYCMD=py -3"
)
if not defined PYCMD (
    where python >nul 2>&1 && set "PYCMD=python"
)
if not defined PYCMD (
    echo No usable Python interpreter found. Install Python 3.11+ or uv.
    pause
    exit /b 1
)

set "PYTHONPATH=%~dp0py314_runtime\lib;%PYTHONPATH%"

"%PYCMD%" "%~dp0bl.py" %*
set "RC=%ERRORLEVEL%"
if %RC% EQU 3 (
    echo.
    echo This copy failed the TFast Digital brand integrity check and was blocked.
    echo ^(c^) 2025-2026 TFast Digital Agency. https://tfastdigital.com/
    pause
    exit /b 3
)
if %RC% NEQ 0 (
    echo.
    echo ^(c^) 2025-2026 TFast Digital Agency. All rights reserved.
    echo https://tfastdigital.com/
    pause
)
endlocal
exit /b %RC%
