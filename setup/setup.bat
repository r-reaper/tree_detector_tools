@echo off
echo Setting up Python virtual environment for the QGIS Tree Detector plugin.
setlocal

REM Get the directory where the script is located
set SETUP_DIR=%~dp0
REM *** FIX: Define config dir in a standard user location ***
set CONFIG_DIR=%USERPROFILE%\\.tree_detector_plugin
set VENV_DIR=%CONFIG_DIR%\\venv
set CONFIG_FILE=%CONFIG_DIR%\\config.txt

echo Setting up Python virtual environment at: %VENV_DIR%
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

REM Check for Python 3
py -3 --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python 3 is not installed or not in PATH.
    echo Please install Python 3 (from python.org) and ensure it's added to your PATH.
    pause
    exit /b 1
)

REM Create virtual environment
py -3 -m venv "%VENV_DIR%"

REM Check if venv was created successfully
if not exist "%VENV_DIR%\\Scripts\\activate.bat" (
    echo Error: Failed to create the virtual environment.
    pause
    exit /b 1
)

REM Activate the environment and install packages
echo Activating environment and installing required packages...
call "%VENV_DIR%\\Scripts\\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r "%SETUP_DIR%requirements.txt"

REM Check if installation was successful
if %errorlevel% equ 0 (
    REM Write the absolute path of the python executable to the config file
    set VENV_PYTHON_PATH=%VENV_DIR%\\Scripts\\python.exe
    echo Writing python path to config: %CONFIG_FILE%
    echo %VENV_PYTHON_PATH% > %CONFIG_FILE%

    echo.
    echo --------------------------------------------------
    echo Setup complete!
    echo The processing environment is ready.
    echo You can now install the 'tree_detector_tools' folder into QGIS.
    echo --------------------------------------------------
) else (
    echo.
    echo --------------------------------------------------
    echo Error: Package installation failed.
    echo Please check the error messages above.
    echo --------------------------------------------------
)

deactivate
pause