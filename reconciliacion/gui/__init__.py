"""La interfaz.

La ventana se importa de forma perezosa a proposito. Si la importara de entrada,
cualquiera que quisiera probar el hilo de trabajo necesitaria un entorno grafico
disponible; asi las pruebas corren en cualquier parte, incluida la maquina de
integracion continua, que no tiene pantalla.
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
