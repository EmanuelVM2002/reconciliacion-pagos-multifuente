"""Deteccion de fraude sobre el universo reconciliado.

El fraude es una dimension **independiente** de la clasificacion: una
transaccion puede estar `RECONCILIADO` y aun asi ser fraude, por eso ambas
viven en columnas distintas de la misma fila.

A diferencia de las reglas de clasificacion, que miran una transaccion a la
vez, tres de los cuatro patrones necesitan ver **todo el conjunto**: el umbral
de monto anomalo se calcula sobre la distribucion completa y el patron
sospechoso compara unas transacciones contra otras. Por eso el contrato aqui
recibe la coleccion entera y no una transaccion suelta.
"""

from __future__ import annotations

import statistics
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Sequence, Tuple

from reconciliacion.dominio.enums import NivelRiesgo, TipoFraude
from reconciliacion.dominio.transaccion import TransaccionReconciliada
from reconciliacion.log import obtener_logger
from reconciliacion.procesamiento.reglas import formatear_monto

_log = obtener_logger(__name__)

#: Numero de desviaciones estandar a partir del cual un monto se considera anomalo.
SIGMAS_MONTO_ANOMALO = 3

#: Ultima hora (inclusive) de la franja horaria considerada inusual: 00:00-05:59.
HORA_LIMITE_INUSUAL = 5

#: Ventana dentro de la cual dos transacciones gemelas resultan sospechosas.
VENTANA_PATRON = timedelta(minutes=60)


@dataclass
class ResumenFraude:
    """Indicadores agregados de la deteccion de fraude, para la interfaz.

    Attributes:
        total_fraudes: Transacciones con al menos un patron detectado.
        por_tipo: Conteo por tipo de fraude (una transaccion puede sumar en
            varios).
        por_nivel: Conteo por nivel de riesgo.
        monto_en_riesgo: Suma de los montos de referencia de las transacciones
            marcadas como fraude.
        umbral_monto: Umbral de monto anomalo calculado (media + 3 sigma).
    """

    total_fraudes: int = 0
    por_tipo: Dict[str, int] = field(default_factory=dict)
    por_nivel: Dict[str, int] = field(default_factory=dict)
    monto_en_riesgo: float = 0.0
    umbral_monto: float = 0.0


class ReglaFraude(ABC):
    """Contrato de un patron de fraude.

    Recibe el universo completo porque la mayoria de los patrones son
    estadisticos o relacionales y no se pueden evaluar transaccion por
    transaccion de forma aislada.
    """

    @abstractmethod
    def detectar(self, transacciones: Sequence[TransaccionReconciliada]) -> None:
        """Marca las transacciones que cumplen el patron.

        Args:
            transacciones: Universo reconciliado, modificado en sitio.
        """

    @staticmethod
    def _marcar(
        transaccion: TransaccionReconciliada,
        tipo: TipoFraude,
        observacion: str,
    ) -> None:
        """Asigna un tipo de fraude a una transaccion, sin duplicar.

        Args:
            transaccion: Transaccion a marcar.
            tipo: Patron detectado.
            observacion: Explicacion legible del hallazgo.
        """
        if tipo not in transaccion.tipos_fraude:
            transaccion.tipos_fraude.append(tipo)
            transaccion.observaciones.append(observacion)


class ReglaMontoAnomalo(ReglaFraude):
    """Marca los montos que se salen de la distribucion del conjunto.

    Se considera anomalo todo monto de referencia mayor que
    ``media + 3 * sigma``, calculadas sobre los montos de referencia de **todas**
    las transacciones del universo.

    Se usa la desviacion **poblacional** y no la muestral porque el conjunto
    analizado no es una muestra de algo mayor: es la poblacion completa de
    transacciones del periodo. Sobre estos datos ambas dan el mismo resultado
    (11 transacciones), asi que la eleccion no cambia la salida, pero conviene
    que el criterio sea explicito.

    Attributes:
        umbral: Ultimo umbral calculado, expuesto para mostrarlo en la interfaz.
    """

    def __init__(self) -> None:
        """Crea la regla con el umbral aun sin calcular."""
        self.umbral: float = 0.0

    def detectar(self, transacciones: Sequence[TransaccionReconciliada]) -> None:
        """Calcula el umbral y marca las transacciones que lo superan."""
        montos = [t.monto_referencia for t in transacciones if t.monto_referencia is not None]
        if len(montos) < 2:
            return

        media = statistics.mean(montos)
        sigma = statistics.pstdev(montos)
        self.umbral = media + SIGMAS_MONTO_ANOMALO * sigma

        _log.info(
            "Umbral de monto anomalo: %s (media %s + %d sigma %s)",
            formatear_monto(self.umbral),
            formatear_monto(media),
            SIGMAS_MONTO_ANOMALO,
            formatear_monto(sigma),
        )

        for transaccion in transacciones:
            monto = transaccion.monto_referencia
            if monto is not None and monto > self.umbral:
                self._marcar(
                    transaccion,
                    TipoFraude.MONTO,
                    f"Monto {formatear_monto(monto)} supera el umbral de "
                    f"{formatear_monto(self.umbral)} (media + 3 sigma).",
                )


class ReglaHoraInusual(ReglaFraude):
    """Marca las transacciones ocurridas de madrugada (00:00 a 05:59)."""

    def detectar(self, transacciones: Sequence[TransaccionReconciliada]) -> None:
        """Marca las transacciones cuya fecha de referencia cae en la franja."""
        for transaccion in transacciones:
            fecha = transaccion.fecha_referencia
            if fecha is not None and fecha.hour <= HORA_LIMITE_INUSUAL:
                self._marcar(
                    transaccion,
                    TipoFraude.HORA,
                    f"Transaccion a las {fecha:%H:%M} (franja inusual 00:00-05:59).",
                )


class ReglaPatronSospechoso(ReglaFraude):
    """Marca transacciones gemelas y proximas en el tiempo.

    Dos o mas transacciones del **mismo banco** por el **mismo monto de
    referencia** cuyas fechas caen dentro de una ventana de 60 minutos o menos
    resultan sospechosas de fraccionamiento o duplicacion. Se marcan todas las
    involucradas, no solo la segunda.
    """

    def detectar(self, transacciones: Sequence[TransaccionReconciliada]) -> None:
        """Agrupa por banco y monto y busca coincidencias dentro de la ventana."""
        grupos: Dict[Tuple[str, float], List[TransaccionReconciliada]] = defaultdict(list)
        for transaccion in transacciones:
            monto = transaccion.monto_referencia
            if transaccion.banco and monto is not None and transaccion.fecha_referencia:
                grupos[(transaccion.banco, monto)].append(transaccion)

        for (banco, monto), grupo in grupos.items():
            if len(grupo) < 2:
                continue
            grupo.sort(key=lambda t: t.fecha_referencia)  # type: ignore[arg-type,return-value]

            relacionadas: Dict[int, List[str]] = defaultdict(list)
            for i in range(len(grupo)):
                for j in range(i + 1, len(grupo)):
                    distancia = grupo[j].fecha_referencia - grupo[i].fecha_referencia  # type: ignore[operator]
                    if distancia > VENTANA_PATRON:
                        # El grupo esta ordenado: si esta ya no entra, las
                        # siguientes tampoco.
                        break
                    relacionadas[i].append(grupo[j].id_transaccion)
                    relacionadas[j].append(grupo[i].id_transaccion)

            for indice, pares in relacionadas.items():
                transaccion = grupo[indice]
                self._marcar(
                    transaccion,
                    TipoFraude.PATRON,
                    f"Mismo banco ({banco}) y mismo monto ({formatear_monto(monto)}) "
                    f"que {', '.join(sorted(pares))} en menos de 60 minutos.",
                )


class ReglaSinAutorizacion(ReglaFraude):
    """Marca los movimientos bancarios que nadie autorizo.

    Es el patron mas grave: el banco movio dinero por una transaccion que no
    existe en el archivo de autorizaciones.
    """

    def detectar(self, transacciones: Sequence[TransaccionReconciliada]) -> None:
        """Marca las transacciones presentes en el JSON pero ausentes del CSV."""
        for transaccion in transacciones:
            if transaccion.presente_json and not transaccion.presente_csv:
                movimiento = transaccion.movimiento
                referencia = f" ({movimiento.id_movimiento})" if movimiento else ""
                self._marcar(
                    transaccion,
                    TipoFraude.NO_AUTORIZADO,
                    f"Movimiento bancario{referencia} sin autorizacion previa.",
                )


class DetectorFraude:
    """Aplica todos los patrones de fraude sobre el universo reconciliado.

    Attributes:
        reglas: Patrones a evaluar. Se pueden inyectar otros para extender el
            comportamiento o aislar uno solo en los tests.
    """

    def __init__(self, reglas: Sequence[ReglaFraude] | None = None) -> None:
        """Crea el detector.

        Args:
            reglas: Patrones de fraude. Si se omite se usan los cuatro del
                enunciado.
        """
        self.regla_monto = ReglaMontoAnomalo()
        self.reglas: Tuple[ReglaFraude, ...] = (
            tuple(reglas)
            if reglas is not None
            else (
                self.regla_monto,
                ReglaHoraInusual(),
                ReglaPatronSospechoso(),
                ReglaSinAutorizacion(),
            )
        )

    def detectar(
        self, transacciones: Sequence[TransaccionReconciliada]
    ) -> ResumenFraude:
        """Evalua todos los patrones y devuelve los indicadores agregados.

        Args:
            transacciones: Universo reconciliado, modificado en sitio.

        Returns:
            El resumen de la deteccion.
        """
        for regla in self.reglas:
            regla.detectar(transacciones)

        return self._resumir(transacciones)

    def _resumir(self, transacciones: Sequence[TransaccionReconciliada]) -> ResumenFraude:
        """Calcula los indicadores agregados de fraude.

        Args:
            transacciones: Universo ya evaluado.

        Returns:
            El resumen con conteos por tipo y por nivel de riesgo.
        """
        resumen = ResumenFraude(umbral_monto=self.regla_monto.umbral)

        for transaccion in transacciones:
            if not transaccion.es_fraude:
                continue

            resumen.total_fraudes += 1
            resumen.monto_en_riesgo += transaccion.monto_referencia or 0.0

            for tipo in transaccion.tipos_fraude:
                resumen.por_tipo[str(tipo)] = resumen.por_tipo.get(str(tipo), 0) + 1

            nivel: NivelRiesgo | None = transaccion.nivel_riesgo
            if nivel is not None:
                resumen.por_nivel[str(nivel)] = resumen.por_nivel.get(str(nivel), 0) + 1

            _log.info(
                "FRAUDE %s [%s] %s",
                transaccion.id_transaccion,
                ";".join(str(t) for t in transaccion.tipos_fraude),
                transaccion.nivel_riesgo,
            )

        return resumen
