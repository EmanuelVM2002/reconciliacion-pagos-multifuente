"""Lo que el hilo le dice a la ventana.

Un tipo por cada cosa que puede pasar —avance, linea de log, error, cancelacion,
fin— en vez de tuplas sueltas. Asi el bucle de la interfaz se lee de corrido y
agregar un aviso nuevo manana no rompe lo que ya esta.
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
