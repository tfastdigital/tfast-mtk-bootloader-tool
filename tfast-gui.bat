@echo off
setlocal EnableExtensions
title TFast MTK Bootloader Tool - Desktop Edition
cd /d "%~dp0"

if not exist "%~dp0gui.py" (
    echo gui.py not found next to this launcher.
    pause
    exit /b 1
)

rem ---------------------------------------------------------------
rem Locate a real Python interpreter.
rem NOTE: variable values keep their own quotes so paths with
rem       spaces (e.g. "eng B") survive expansion.
rem ---------------------------------------------------------------
set "PYCMD="

rem 1) uv-managed CPython 3.14 (same generation as the bundled runtime)
for /d %%D in ("%APPDATA%\uv\python\cpython-3.14*") do (
    if exist "%%~fD\python.exe" set "PYCMD="%%~fD\python.exe""
)

rem 2) any uv-managed CPython
if not defined PYCMD (
    for /d %%D in ("%APPDATA%\uv\python\cpython-3*") do (
        if exist "%%~fD\python.exe" set "PYCMD="%%~fD\python.exe""
    )
)

rem 3) py launcher
if not defined PYCMD (
    py -3 -c "import sys" >nul 2>&1 && set "PYCMD=py -3"
)

rem 4) plain python on PATH
if not defined PYCMD (
    where python >nul 2>&1 && set "PYCMD=python"
)

if not defined PYCMD (
    echo No usable Python interpreter was found.
    echo.
    echo Install Python 3.11 or newer, or install uv:
    echo     winget install astral-sh.uv
    echo.
    pause
    exit /b 1
)

rem Bundled third-party libs (requests, pyserial, Pillow, ...)
set "PYTHONPATH=%~dp0py314_runtime\lib;%PYTHONPATH%"

%PYCMD% "%~dp0gui.py" %*
if errorlevel 1 (
    echo.
    echo The GUI exited with an error. Review the message above.
    echo ^(c^) 2025-2026 TFast Digital Agency. https://tfastdigital.com/
    pause
)
endlocal
