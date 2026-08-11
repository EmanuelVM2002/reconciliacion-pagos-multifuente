"""Abrir la ventana.

    python ejecutar_gui.py

En Windows tambien sirve el doble clic sobre `ejecutar_gui.bat`, que es lo que
usa quien no quiere saber nada de terminales.
"""

from __future__ import annotations

from reconciliacion.gui import lanzar

if __name__ == "__main__":
    lanzar()
