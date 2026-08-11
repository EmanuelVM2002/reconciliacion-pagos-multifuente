"""Configuracion del sistema de logs del proyecto.

Todo el codigo de negocio registra sus hallazgos con `logging` estandar y
nunca imprime a consola. Eso permite que el mismo codigo sirva sin cambios
para el script de consola y para la interfaz grafica: la GUI simplemente
engancha su propio `Handler` al logger raiz del paquete y recibe los mensajes
mientras el proceso corre.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

NOMBRE_LOGGER_RAIZ = "reconciliacion"

_FORMATO = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_FORMATO_FECHA = "%H:%M:%S"


def obtener_logger(nombre: Optional[str] = None) -> logging.Logger:
    """Devuelve el logger del paquete o uno de sus hijos.

    Args:
        nombre: Nombre del submodulo (normalmente `__name__`). Si es None se
            devuelve el logger raiz del paquete.

    Returns:
        El logger correspondiente, ya colgado del arbol `reconciliacion.*`.
    """
    if nombre is None or nombre == NOMBRE_LOGGER_RAIZ:
        return logging.getLogger(NOMBRE_LOGGER_RAIZ)
    corto = nombre.split(".")[-1]
    return logging.getLogger(f"{NOMBRE_LOGGER_RAIZ}.{corto}")


def configurar_consola(nivel: int = logging.INFO) -> logging.Logger:
    """Configura la salida de logs por consola para la ejecucion por terminal.

    La interfaz grafica NO llama a esta funcion: ella instala su propio
    handler para no escribir en una consola que el usuario final no ve.

    Args:
        nivel: Nivel minimo a mostrar.

    Returns:
        El logger raiz del paquete, ya configurado.
    """
    # La consola de Windows suele venir en cp1252 y fallaria al escribir
    # acentos (por ejemplo el nivel de riesgo "CRITICO" con tilde). Se fuerza
    # UTF-8 tolerante para que un problema de codificacion nunca tumbe el
    # proceso.
    for flujo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(flujo, "reconfigure", None)
        if reconfigurar is not None:
            try:
                reconfigurar(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - depende del terminal
                pass

    logger = logging.getLogger(NOMBRE_LOGGER_RAIZ)
    logger.setLevel(nivel)
    logger.propagate = False
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FORMATO, datefmt=_FORMATO_FECHA))
        logger.addHandler(handler)
    return logger
