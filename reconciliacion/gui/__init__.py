"""Interfaz grafica (Tkinter + customtkinter).

La ventana se importa de forma perezosa a proposito. Importar este paquete
arrastraria `customtkinter` y con el todo `tkinter`, que exige un entorno
grafico disponible; el hilo de trabajo, en cambio, solo habla con una cola y
se puede probar en cualquier parte, incluida una maquina de integracion
continua sin pantalla. Separarlos evita que una prueba del trabajador dependa
de que exista un escritorio.
"""

from typing import Any

from reconciliacion.gui.mensajes import Mensaje, TipoMensaje
from reconciliacion.gui.trabajador import ManejadorCola, TrabajadorReconciliacion

__all__ = [
    "AplicacionReconciliacion",
    "ManejadorCola",
    "Mensaje",
    "TipoMensaje",
    "TrabajadorReconciliacion",
    "lanzar",
]

_PEREZOSOS = {"AplicacionReconciliacion", "lanzar"}


def __getattr__(nombre: str) -> Any:
    """Carga la ventana solo cuando alguien la pide de verdad.

    Args:
        nombre: Atributo solicitado del paquete.

    Returns:
        El objeto pedido, importado en ese momento.

    Raises:
        AttributeError: Si el atributo no existe en el paquete.
    """
    if nombre in _PEREZOSOS:
        from reconciliacion.gui import app

        return getattr(app, nombre)
    raise AttributeError(f"El paquete no expone '{nombre}'.")
