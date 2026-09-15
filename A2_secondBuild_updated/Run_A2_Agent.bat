@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
    if not errorlevel 1 goto install
)

set "PYTHON_CMD="
set "PYTHON_ARGS="
call :try_python python
if defined PYTHON_CMD goto create_venv
call :try_python python3
if defined PYTHON_CMD goto create_venv
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py"
    set "PYTHON_ARGS=-3"
    goto create_venv
)
call :try_python python3.13
if defined PYTHON_CMD goto create_venv
call :try_python python3.12
if defined PYTHON_CMD goto create_venv
call :try_python python3.11
if defined PYTHON_CMD goto create_venv
call :try_python python3.10
if defined PYTHON_CMD goto create_venv
call :try_python python3.9
if defined PYTHON_CMD goto create_venv

for %%P in (
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%LocalAppData%\Programs\Python\Python310\python.exe"
    "%LocalAppData%\Programs\Python\Python39\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
    "%ProgramFiles%\Python310\python.exe"
    "%ProgramFiles%\Python39\python.exe"
) do (
    if exist "%%~P" (
        "%%~P" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_CMD=%%~P"
            goto create_venv
        )
    )
)

:ask_python
echo.
echo A compatible Python executable was not detected automatically.
echo Enter the full path to a Python 3.9 or newer executable.
echo No Python installation will be attempted.
set "USER_PY="
set /p "USER_PY=Python executable path, or B to exit: "
set "USER_PY=%USER_PY:"=%"
if /i "%USER_PY%"=="B" exit /b 0
if not exist "%USER_PY%" (
    echo That file does not exist.
    goto ask_python
)
"%USER_PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if errorlevel 1 (
    echo That executable is not Python 3.9 or newer.
    goto ask_python
)
set "PYTHON_CMD=%USER_PY%"
set "PYTHON_ARGS="

:create_venv
echo Preparing the private project environment...
"%PYTHON_CMD%" %PYTHON_ARGS% -m venv --clear "%CD%\.venv"
if errorlevel 1 goto failed

:install
echo Checking project dependencies...
"%VENV_PY%" -m pip install --disable-pip-version-check --quiet -r "%CD%\requirements.txt"
if errorlevel 1 goto failed

echo Starting the PE6201 A2 Agent...
"%VENV_PY%" "%CD%\main.py"
set "RUN_STATUS=%ERRORLEVEL%"
if not "%RUN_STATUS%"=="0" (
    echo.
    echo The agent stopped with exit code %RUN_STATUS%.
)
echo.
pause
exit /b %RUN_STATUS%

:try_python
%* -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=%*"
exit /b 0

:failed
echo.
echo Setup did not complete. You can close this window safely and run this file again.
echo A later run will repair the private environment before starting.
pause
exit /b 1
