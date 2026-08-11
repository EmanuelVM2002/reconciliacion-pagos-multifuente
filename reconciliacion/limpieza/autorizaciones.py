"""Conversion de las filas crudas del CSV en autorizaciones limpias.

Este modulo orquesta a los tres extractores especializados (`montos`,
`marcas`, `retenciones`) y es el unico punto donde una `FilaAutorizacionCruda`
se convierte en una `Autorizacion` utilizable por la reconciliacion.

Criterio de tolerancia a fallos: una fila que no se pueda parsear del todo
**no se descarta**. Se conserva con el campo en `None` y se registra una
incidencia, porque perder filas en silencio es el peor resultado posible en un
proceso contable: es preferible una transaccion visible e incompleta que una
transaccion ausente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

from reconciliacion.dominio.modelos import Autorizacion, FilaAutorizacionCruda
from reconciliacion.limpieza.fechas import parsear_fecha
from reconciliacion.limpieza.marcas import extraer_marca
from reconciliacion.limpieza.montos import extraer_monto, extraer_montos
from reconciliacion.limpieza.retenciones import entidades_desconocidas, extraer_retenciones
from reconciliacion.log import obtener_logger

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


def limpiar_autorizaciones(filas: Sequence[FilaAutorizacionCruda]) -> ResultadoLimpieza:
    """Limpia el lote completo de filas crudas del CSV.

    Args:
        filas: Filas leidas por el cargador del CSV.

    Returns:
        El resultado con las autorizaciones limpias y el detalle de incidencias.
    """
    resultado = ResultadoLimpieza(filas_procesadas=len(filas))

    for fila in filas:
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
