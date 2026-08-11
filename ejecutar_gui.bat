@echo off
REM Abre la interfaz grafica con doble clic, sin pasar por la terminal.
REM Usa el entorno virtual del proyecto si existe; si no, el Python del sistema.

cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "ejecutar_gui.py"
) else (
    start "" pythonw "ejecutar_gui.py"
)
