"""Excepciones propias del proyecto.

Se declara una jerarquia propia para que la interfaz grafica pueda distinguir
un problema *previsible* del negocio (falta un archivo, una fuente esta
corrupta) de un fallo inesperado del programa, y traducir el primero a un
mensaje en el idioma del usuario final en vez de mostrar un traceback.
"""

from __future__ import annotations


class ErrorReconciliacion(Exception):
    """Error base del proyecto. Todo error previsible hereda de aqui."""

    def __init__(self, mensaje: str, detalle: str = "") -> None:
        """Crea el error.

        Args:
            mensaje: Texto apto para mostrar al usuario final.
            detalle: Informacion tecnica adicional para el log.
        """
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalle = detalle


class FuenteNoDisponibleError(ErrorReconciliacion):
    """No se encontro el archivo de una fuente de datos."""


class FuenteCorruptaError(ErrorReconciliacion):
    """El archivo existe pero no se pudo leer (formato o estructura invalida)."""


class ErrorExportacion(ErrorReconciliacion):
    """No se pudo escribir el reporte de salida."""


class ProcesoCancelado(ErrorReconciliacion):
    """El usuario detuvo el proceso antes de que terminara.

    No es un fallo: hereda de `ErrorReconciliacion` para viajar por el mismo
    camino de interrupcion, pero quien lo atrape debe tratarlo como una
    decision del usuario y no como un error que reportar.
    """
