"""Mensajes que el hilo de trabajo envia a la interfaz.

Tkinter no es seguro para hilos: solo el hilo que creo los widgets puede
tocarlos. Por eso el trabajo pesado nunca escribe en la ventana; se comunica
con ella a traves de una cola de estos mensajes, que la interfaz vacia a su
propio ritmo.

Usar un tipo explicito en vez de tuplas sueltas hace que el bucle de la
interfaz sea un `match` legible y que agregar un tipo de aviso manana no rompa
lo que ya existe.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from reconciliacion.servicio import ResultadoProceso


class TipoMensaje(Enum):
    """Naturaleza de un mensaje enviado desde el hilo de trabajo."""

    PROGRESO = auto()
    """Avance del proceso: mueve la barra y actualiza el paso actual."""

    LOG = auto()
    """Linea de detalle para la bitacora en pantalla."""

    ERROR = auto()
    """Fallo previsible: se muestra al usuario y se libera la interfaz."""

    FIN = auto()
    """Proceso terminado con exito: trae el resultado completo."""

    CANCELADO = auto()
    """El usuario detuvo el proceso. No es un error y se informa distinto."""


@dataclass(frozen=True)
class Mensaje:
    """Un aviso del hilo de trabajo hacia la interfaz.

    Attributes:
        tipo: Naturaleza del aviso.
        texto: Mensaje legible para el usuario.
        porcentaje: Avance acumulado (solo en `PROGRESO`).
        detalle: Informacion tecnica adicional (solo en `ERROR`).
        resultado: Resultado del proceso (solo en `FIN`).
    """

    tipo: TipoMensaje
    texto: str = ""
    porcentaje: float = 0.0
    detalle: str = ""
    resultado: Optional[ResultadoProceso] = None
