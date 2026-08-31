@echo off
chcp 65001 >nul
title Сборка BarcodeDecoder в единый .EXE (UPX)

echo ======================================================================
echo    Сборка BarcodeDecoder v1.1 в единый .EXE файл с сжатием UPX
echo ======================================================================
echo.

:: Определение рабочей директории скрипта
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Поиск виртуального окружения Python
set "PYTHON_EXE="
if exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%\.venv\Scripts\python.exe"
) else if exist "%SCRIPT_DIR%\..\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%\..\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [1/4] Проверка Python окружения: %PYTHON_EXE%
"%PYTHON_EXE%" --version
if errorlevel 1 (
    echo [ОШИБКА] Python не найден! Убедитесь, что Python установлен.
    pause
    exit /b 1
)

:: Проверка наличия PyInstaller
echo [2/4] Проверка PyInstaller...
"%PYTHON_EXE%" -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller не установлен. Выполняется установка...
    "%PYTHON_EXE%" -m pip install pyinstaller
)

:: Проверка UPX
echo [3/4] Проверка UPX упаковщика...
where upx >nul 2>&1
if errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] UPX не найден в PATH. Сборка будет выполнена без UPX сжатия.
    set "UPX_ARG="
) else (
    echo UPX найден в системе.
    set "UPX_ARG=--upx-dir=\"%LOCALAPPDATA%\Microsoft\WindowsApps\""
)

:: Определение путей исходного файла и папок сборки
if exist "%SCRIPT_DIR%\BarcodeDecoder\BarcodeDecoder_1.1.py" (
    set "SOURCE_FILE=%SCRIPT_DIR%\BarcodeDecoder\BarcodeDecoder_1.1.py"
    set "DIST_DIR=%SCRIPT_DIR%\BarcodeDecoder\dist"
    set "WORK_DIR=%SCRIPT_DIR%\BarcodeDecoder\build"
    set "SPEC_DIR=%SCRIPT_DIR%\BarcodeDecoder"
) else if exist "%SCRIPT_DIR%\BarcodeDecoder_1.1.py" (
    set "SOURCE_FILE=%SCRIPT_DIR%\BarcodeDecoder_1.1.py"
    set "DIST_DIR=%SCRIPT_DIR%\dist"
    set "WORK_DIR=%SCRIPT_DIR%\build"
    set "SPEC_DIR=%SCRIPT_DIR%"
) else (
    echo [ОШИБКА] Исходный файл BarcodeDecoder_1.1.py не найден!
    pause
    exit /b 1
)

echo [4/4] Запуск компиляции PyInstaller (Single File)...
"%PYTHON_EXE%" -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "BarcodeDecoder" ^
    --clean ^
    %UPX_ARG% ^
    --exclude-module unittest ^
    --exclude-module test ^
    --exclude-module pydoc ^
    --exclude-module doctest ^
    --exclude-module sqlite3 ^
    --exclude-module xmlrpc ^
    --exclude-module multiprocessing ^
    --exclude-module asyncio ^
    --exclude-module concurrent ^
    --exclude-module curses ^
    --exclude-module distutils ^
    --exclude-module lib2to3 ^
    --exclude-module pdb ^
    --exclude-module setuptools ^
    --distpath "%DIST_DIR%" ^
    --workpath "%WORK_DIR%" ^
    --specpath "%SPEC_DIR%" ^
    "%SOURCE_FILE%"

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Во время компиляции произошла ошибка!
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo [УСПЕХ] Сборка успешно завершена!
echo Исполняемый файл: %DIST_DIR%\BarcodeDecoder.exe
echo ======================================================================
echo.
pause
