@echo off
cd /d "%~dp0"
echo.
echo  CIRCULAR MUSIC - Instalacion e inicio
py --version >nul 2>&1
if errorlevel 1 (
    echo Python no se encuentra. Instala Python para Windows y vuelve a intentar.
    pause
    exit /b 1
)
py -m pip install -r requirements.txt
if errorlevel 1 (
    echo No se pudieron instalar las dependencias.
    pause
    exit /b 1
)
py main.py
if errorlevel 1 (
    echo La aplicacion termino con un error. Revisa los mensajes anteriores.
    pause
)
