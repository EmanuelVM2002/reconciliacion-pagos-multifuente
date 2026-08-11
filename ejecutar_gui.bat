@echo off
REM Abre la interfaz grafica con doble clic, sin pasar por la terminal.
REM
REM Se lanza con pythonw (sin ventana de consola), pero pythonw tampoco muestra
REM errores: si faltara Python o una dependencia, el doble clic no haria
REM absolutamente nada y la persona no sabria por que. Por eso antes de lanzar
REM se hace una comprobacion con el interprete normal y, si algo falta, se
REM explica en pantalla y se espera a que lea el mensaje.

setlocal
cd /d "%~dp0"

REM Prefiere el entorno virtual del proyecto; si no existe, usa el del sistema.
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
    set "PYW=.venv\Scripts\pythonw.exe"
) else (
    set "PY=python"
    set "PYW=pythonw"
)

"%PY%" -c "import customtkinter, openpyxl" >nul 2>&1
if errorlevel 1 goto faltan_requisitos

start "" "%PYW%" "ejecutar_gui.py"
exit /b 0

:faltan_requisitos
echo.
echo  No se pudo abrir la aplicacion.
echo.
echo  Falta Python o alguna de sus dependencias. Abre una terminal en esta
echo  carpeta y ejecuta:
echo.
echo      pip install -r requirements.txt
echo.
pause
exit /b 1
