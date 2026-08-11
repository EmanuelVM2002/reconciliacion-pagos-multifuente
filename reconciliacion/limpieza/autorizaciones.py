"""Junta los tres extractores y arma la autorizacion limpia.

Aqui es donde una fila cruda del CSV se convierte en algo usable.

La decision que sostengo: **una fila que no se pueda parsear no se tira**. Se
queda con el campo vacio y deja una incidencia en el log. En un proceso contable
prefiero mil veces una transaccion visible e incompleta que una transaccion que
desaparecio sin que nadie se diera cuenta.

Los contadores del resultado (`sin_monto`, `sin_marca`, ...) existen justo para
poder demostrar eso cuando termina.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from reconciliacion.dominio.modelos import Autorizacion, FilaAutorizacionCruda
from reconciliacion.limpieza.fechas import parsear_fecha
from reconciliacion.limpieza.marcas import extraer_marca
from reconciliacion.limpieza.montos import extraer_monto, extraer_montos
from reconciliacion.limpieza.retenciones import entidades_desconocidas, extraer_retenciones
from reconciliacion.log import obtener_logger
from reconciliacion.progreso import ProgresoParcial, notificar

_log = obtener_logger(__name__)


@dataclass
class ResultadoLimpieza:
    """Resultado de limpiar el lote completo de autorizaciones.

    Los contadores permiten demostrar, al final del proceso, que se extrajo
    monto, marca y retenciones para **todas** las filas del CSV.

    Attributes:
        autorizaciones: Autorizaciones ya limpias.
        incidencias: Problemas puntuales de parseo, uno por linea de texto.
        filas_procesadas: Filas crudas recibidas.
        sin_monto: Filas de las que no se pudo extraer el monto.
        sin_marca: Filas de las que no se pudo extraer la marca.
        sin_retenciones: Filas sin ninguna retencion reconocible.
        sin_fecha: Filas con fecha ilegible.
        con_monto_duplicado: Filas donde la clave `monto` aparecia repetida
            con valores distintos y se aplico la regla de "gana el ultimo".
    """

    autorizaciones: List[Autorizacion] = field(default_factory=list)
    incidencias: List[str] = field(default_factory=list)
    filas_procesadas: int = 0
    sin_monto: int = 0
    sin_marca: int = 0
    sin_retenciones: int = 0
    sin_fecha: int = 0
    con_monto_duplicado: int = 0

    @property
    def extraccion_completa(self) -> bool:
        """Indica si se extrajo monto, marca y retenciones de todas las filas."""
        return not (self.sin_monto or self.sin_marca or self.sin_retenciones)

    def resumen(self) -> str:
        """Devuelve una linea de resumen apta para el log y la interfaz."""
        return (
            f"{len(self.autorizaciones)}/{self.filas_procesadas} autorizaciones limpias "
            f"(sin monto: {self.sin_monto}, sin marca: {self.sin_marca}, "
            f"sin retenciones: {self.sin_retenciones})"
        )


def construir_autorizacion(fila: FilaAutorizacionCruda) -> tuple[Autorizacion, List[str]]:
    """Convierte una fila cruda del CSV en una autorizacion limpia.

    Args:
        fila: Fila tal como se leyo del archivo.

    Returns:
        La autorizacion resultante y la lista de incidencias detectadas al
        parsearla (vacia si todo se extrajo correctamente).
    """
    incidencias: List[str] = []

    montos = extraer_montos(fila.monto_crudo)
    monto = montos[-1] if montos else None
    if monto is None:
        incidencias.append(f"Fila {fila.numero_fila} ({fila.id_transaccion}): monto no extraible.")
    elif len(set(montos)) > 1:
        # Clave `monto` repetida con valores distintos: se conserva el ultimo,
        # que es la semantica estandar de JSON ante claves duplicadas.
        incidencias.append(
            f"{fila.id_transaccion}: clave 'monto' duplicada con valores {montos}; "
            f"se toma el ultimo ({monto:,.0f})."
        )

    marca = extraer_marca(fila.marca_cruda)
    if marca is None:
        incidencias.append(f"Fila {fila.numero_fila} ({fila.id_transaccion}): marca no extraible.")

    retenciones = extraer_retenciones(fila.marca_cruda)
    if not retenciones:
        incidencias.append(f"{fila.id_transaccion}: sin retenciones reconocibles.")

    desconocidas = entidades_desconocidas(retenciones)
    if desconocidas:
        incidencias.append(
            f"{fila.id_transaccion}: entidad(es) de retencion no catalogada(s): "
            f"{', '.join(desconocidas)}."
        )

    fecha = parsear_fecha(fila.fecha_cruda)
    if fecha is None:
        incidencias.append(
            f"{fila.id_transaccion}: fecha ilegible ({fila.fecha_cruda!r})."
        )

    autorizacion = Autorizacion(
        id_transaccion=fila.id_transaccion,
        monto=monto,
        fecha=fecha,
        banco=fila.banco,
        marca=marca,
        estado=fila.estado,
        retenciones=retenciones,
    )
    return autorizacion, incidencias


def limpiar_autorizaciones(
    filas: Sequence[FilaAutorizacionCruda],
    progreso: Optional[ProgresoParcial] = None,
) -> ResultadoLimpieza:
    """Limpia el lote completo de filas crudas del CSV.

    Args:
        filas: Filas leidas por el cargador del CSV.
        progreso: Aviso opcional de avance parcial, para que quien llame pueda
            mostrar el progreso mientras se procesan las filas.

    Returns:
        El resultado con las autorizaciones limpias y el detalle de incidencias.
    """
    resultado = ResultadoLimpieza(filas_procesadas=len(filas))
    total = len(filas)

    for procesadas, fila in enumerate(filas, start=1):
        autorizacion, incidencias = construir_autorizacion(fila)
        resultado.autorizaciones.append(autorizacion)
        resultado.incidencias.extend(incidencias)

        if autorizacion.monto is None:
            resultado.sin_monto += 1
        if autorizacion.marca is None:
            resultado.sin_marca += 1
        if not autorizacion.retenciones:
            resultado.sin_retenciones += 1
        if autorizacion.fecha is None:
            resultado.sin_fecha += 1
        if len(set(extraer_montos(fila.monto_crudo))) > 1:
            resultado.con_monto_duplicado += 1

        notificar(progreso, procesadas, total)

    _log.info("Limpieza del CSV: %s", resultado.resumen())
    for incidencia in resultado.incidencias:
        _log.warning("Limpieza: %s", incidencia)

    return resultado


__all__ = [
    "ResultadoLimpieza",
    "construir_autorizacion",
    "extraer_monto",
    "limpiar_autorizaciones",
]
