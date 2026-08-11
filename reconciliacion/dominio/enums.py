"""Vocabulario cerrado del resultado de la reconciliacion.

Se usan enumeraciones en vez de cadenas sueltas para que un error de escritura
falle al importar y no silenciosamente en el Excel, y para que el valor exacto
que se exporta viva en un solo lugar.
"""

from __future__ import annotations

from enum import Enum


class Clasificacion(str, Enum):
    """Etiquetas posibles de una transaccion.

    La clasificacion es **multi-etiqueta**: una transaccion puede faltar en una
    fuente y ademas tener un monto distinto en otra. La unica etiqueta
    excluyente es `RECONCILIADO`, que se usa sola y solo cuando no hay ningun
    hallazgo.
    """

    RECONCILIADO = "RECONCILIADO"
    DISCREPANCIA_MONTO = "DISCREPANCIA_MONTO"
    DISCREPANCIA_ESTADO = "DISCREPANCIA_ESTADO"
    NO_ENCONTRADO_EN_JSON = "NO_ENCONTRADO_EN_JSON"
    NO_CONTABILIZADO = "NO_CONTABILIZADO"
    NO_AUTORIZADO = "NO_AUTORIZADO"

    def __str__(self) -> str:
        """Devuelve el texto que va al reporte."""
        return self.value


class TipoFraude(str, Enum):
    """Patrones de fraude detectables.

    El fraude es una dimension **independiente** de la clasificacion: una
    transaccion puede estar `RECONCILIADO` y aun asi ser fraude.
    """

    MONTO = "FRAUDE_MONTO"
    HORA = "FRAUDE_HORA"
    PATRON = "FRAUDE_PATRON"
    NO_AUTORIZADO = "FRAUDE_NO_AUTORIZADO"

    def __str__(self) -> str:
        """Devuelve el texto que va al reporte."""
        return self.value


class NivelRiesgo(str, Enum):
    """Severidad asignada a una transaccion con fraude.

    Si una transaccion acumula varios fraudes se toma el nivel mas alto. El
    orden de la enumeracion refleja esa prioridad y se usa para comparar.
    """

    CRITICO = "CRÍTICO"
    ALTO = "ALTO"
    MEDIO = "MEDIO"

    def __str__(self) -> str:
        """Devuelve el texto que va al reporte."""
        return self.value


#: Prioridad de cada tipo de fraude: a menor numero, mayor severidad.
PRIORIDAD_RIESGO: dict[TipoFraude, NivelRiesgo] = {
    TipoFraude.NO_AUTORIZADO: NivelRiesgo.CRITICO,
    TipoFraude.MONTO: NivelRiesgo.ALTO,
    TipoFraude.HORA: NivelRiesgo.MEDIO,
    TipoFraude.PATRON: NivelRiesgo.MEDIO,
}

#: Orden de severidad, de mayor a menor.
ORDEN_SEVERIDAD: tuple[NivelRiesgo, ...] = (
    NivelRiesgo.CRITICO,
    NivelRiesgo.ALTO,
    NivelRiesgo.MEDIO,
)
