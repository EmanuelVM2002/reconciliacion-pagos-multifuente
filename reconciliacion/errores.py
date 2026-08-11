"""Mis excepciones.

Les di jerarquia propia para poder separar dos cosas que no son iguales: un
problema previsible del negocio (falta un archivo, la fuente vino corrupta) y un
fallo de programacion. Los primeros la interfaz los atrapa y los traduce a algo
que la persona entiende; los segundos salen como lo que son, un bug.

Cada error lleva dos textos: `mensaje`, que es lo que se muestra en pantalla, y
`detalle`, la parte tecnica que va al log y que solo mira quien lo va a arreglar.
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
