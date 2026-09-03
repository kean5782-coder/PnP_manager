@echo off
chcp 65001 >nul
title Сборка экосистемы SMD Hub и модулей в .EXE

echo ======================================================================
echo       Сборка экосистемы SMD Hub (Launcher, Decoder, Unification, PnP)
echo ======================================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Поиск Python окружения
set "PYTHON_EXE="
py -3.13 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py -3.13"
) else if exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%\.venv\Scripts\python.exe"
) else if exist "%SCRIPT_DIR%\..\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%\..\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [1/4] Проверка Python окружения: %PYTHON_EXE%
%PYTHON_EXE% --version
if errorlevel 1 (
    echo [ОШИБКА] Python не найден!
    pause
    exit /b 1
)

:: Проверка и установка зависимостей
echo [2/4] Проверка библиотек (pandas, openpyxl, pyinstaller)...
%PYTHON_EXE% -m pip install pandas openpyxl pyinstaller >nul 2>&1

set "DIST_DIR=%SCRIPT_DIR%\dist"
set "WORK_DIR=%SCRIPT_DIR%\build"

echo.
echo [3/4] Компиляция Главного Лаунчера SMD_Hub.exe (включая все библиотеки)...
%PYTHON_EXE% -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "SMD_Hub" ^
    --clean ^
    --icon "icon_hub.ico" ^
    --add-data "icon_hub.ico;." ^
    --add-data "icon_hub.png;." ^
    --add-data "FAQ.md;." ^
    --add-data "database.txt;." ^
    --add-data "database.txt;Unification" ^
    --add-data "smd_engine.py;." ^
    --add-data "smd_icons.py;." ^
    --add-data "smd_auth.py;." ^
    --add-data "smd_db.py;." ^
    --add-data "assets;assets" ^
    --add-data "Unification/Unification.py;Unification" ^
    --add-data "PnP_Manager/PnP_Manager.py;PnP_Manager" ^
    --hidden-import openpyxl ^
    --hidden-import pandas ^
    --hidden-import numpy ^
    --hidden-import et_xmlfile ^
    --hidden-import sqlite3 ^
    --distpath "%DIST_DIR%" ^
    --workpath "%WORK_DIR%" ^
    "smd_hub.py"

if errorlevel 1 (
    echo [ОШИБКА] Ошибка компиляции SMD_Hub.exe!
    pause
    exit /b 1
)

echo.
echo [4/4] Компиляция автономного BarcodeDecoder.exe...
%PYTHON_EXE% -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "BarcodeDecoder" ^
    --clean ^
    --icon "icon.ico" ^
    --add-data "icon.ico;." ^
    --add-data "icon.png;." ^
    --add-data "FAQ.md;." ^
    --add-data "database.txt;." ^
    --add-data "smd_engine.py;." ^
    --add-data "smd_icons.py;." ^
    --add-data "assets;assets" ^
    --distpath "%DIST_DIR%" ^
    --workpath "%WORK_DIR%" ^
    "BarcodeDecoder_1.1.py"

if errorlevel 1 (
    echo [ОШИБКА] Ошибка компиляции BarcodeDecoder.exe!
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo [УСПЕХ] Сборка экосистемы успешно завершена!
echo Файлы полностью автономны и работают на любых ПК без Python:
echo  1. %DIST_DIR%\SMD_Hub.exe (Главный сквозной лаунчер)
echo  2. %DIST_DIR%\BarcodeDecoder.exe (Автономный декодер маркировок)
echo ======================================================================
echo.
pause
