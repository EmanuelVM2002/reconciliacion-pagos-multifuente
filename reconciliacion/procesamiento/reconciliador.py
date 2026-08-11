"""Motor de reconciliacion: cruza las tres fuentes y clasifica el resultado.

El universo a analizar es la **union** de los identificadores de las tres
fuentes: toda transaccion presente en al menos una fuente aparece en el
resultado y queda clasificada. El cruce se hace por el identificador
`TRXxxxx`, que cada fuente nombra distinto (`ID_Transaccion`, `Referencia`,
`transaccion_id`); esa traduccion ya la resolvieron los loaders.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from reconciliacion.dominio.enums import Clasificacion
from reconciliacion.dominio.modelos import Autorizacion, Contabilizacion, MovimientoBancario
from reconciliacion.dominio.transaccion import TransaccionReconciliada
from reconciliacion.log import obtener_logger
from reconciliacion.procesamiento.reglas import REGLAS_POR_DEFECTO, ReglaClasificacion
from reconciliacion.progreso import ProgresoParcial, notificar

_log = obtener_logger(__name__)


@dataclass
class ResumenReconciliacion:
    """Indicadores agregados del proceso, para mostrar en la interfaz.

    El enunciado pide expresamente que estos indicadores NO vayan en el Excel
    (que es el detalle fila por fila) sino en la GUI.

    Attributes:
        total: Transacciones del universo.
        reconciliadas: Cuantas quedaron sin ningun hallazgo.
        por_clasificacion: Conteo por etiqueta (una transaccion multi-etiqueta
            suma en cada una de sus etiquetas).
        monto_total: Suma de los montos de referencia del universo.
        monto_en_discrepancia: Suma de las diferencias de monto detectadas.
    """

    total: int = 0
    reconciliadas: int = 0
    por_clasificacion: Dict[str, int] = field(default_factory=dict)
    monto_total: float = 0.0
    monto_en_discrepancia: float = 0.0

    @property
    def porcentaje_reconciliacion(self) -> float:
        """Porcentaje de transacciones sin hallazgos sobre el universo."""
        if not self.total:
            return 0.0
        return self.reconciliadas / self.total * 100


class Reconciliador:
    """Cruza las tres fuentes y aplica las reglas de clasificacion.

    Attributes:
        reglas: Reglas a aplicar, en orden. Se pueden inyectar otras en los
            tests o para extender el comportamiento sin tocar esta clase.
    """

    def __init__(self, reglas: Sequence[ReglaClasificacion] | None = None) -> None:
        """Crea el reconciliador.

        Args:
            reglas: Reglas de clasificacion. Si se omite se usan las de
                `REGLAS_POR_DEFECTO`.
        """
        self.reglas = tuple(reglas) if reglas is not None else REGLAS_POR_DEFECTO

    def reconciliar(
        self,
        autorizaciones: Iterable[Autorizacion],
        contabilizaciones: Iterable[Contabilizacion],
        movimientos: Iterable[MovimientoBancario],
        progreso: Optional[ProgresoParcial] = None,
    ) -> List[TransaccionReconciliada]:
        """Cruza las tres fuentes y devuelve el universo ya clasificado.

        Args:
            autorizaciones: Autorizaciones limpias del CSV.
            contabilizaciones: Registros contables de SQLite.
            movimientos: Movimientos reportados por el banco.
            progreso: Aviso opcional de avance parcial.

        Returns:
            Las transacciones del universo, ordenadas por identificador.
        """
        por_csv = {a.id_transaccion: a for a in autorizaciones}
        por_sqlite = {c.id_transaccion: c for c in contabilizaciones}
        por_json = {m.id_transaccion: m for m in movimientos}

        universo = sorted(set(por_csv) | set(por_sqlite) | set(por_json))
        _log.info(
            "Universo de reconciliacion: %d transacciones "
            "(CSV %d, SQLite %d, JSON %d)",
            len(universo),
            len(por_csv),
            len(por_sqlite),
            len(por_json),
        )

        transacciones = [
            TransaccionReconciliada(
                id_transaccion=identificador,
                autorizacion=por_csv.get(identificador),
                contabilizacion=por_sqlite.get(identificador),
                movimiento=por_json.get(identificador),
            )
            for identificador in universo
        ]

        for procesadas, transaccion in enumerate(transacciones, start=1):
            self._clasificar(transaccion)
            notificar(progreso, procesadas, len(transacciones))

        return transacciones

    def _clasificar(self, transaccion: TransaccionReconciliada) -> None:
        """Aplica todas las reglas a una transaccion y registra el hallazgo.

        Args:
            transaccion: Transaccion a clasificar, modificada en sitio.
        """
        for regla in self.reglas:
            regla.aplicar(transaccion)

        if not transaccion.esta_reconciliada:
            _log.info(
                "%s -> %s | %s",
                transaccion.id_transaccion,
                ";".join(str(c) for c in transaccion.clasificaciones) or "SIN_CLASIFICAR",
                " ".join(transaccion.observaciones),
            )

    @staticmethod
    def resumir(transacciones: Sequence[TransaccionReconciliada]) -> ResumenReconciliacion:
        """Calcula los indicadores agregados del resultado.

        Args:
            transacciones: Universo ya clasificado.

        Returns:
            El resumen con los indicadores para la interfaz.
        """
        conteo: Counter[str] = Counter()
        for transaccion in transacciones:
            for clasificacion in transaccion.clasificaciones:
                conteo[str(clasificacion)] += 1

        return ResumenReconciliacion(
            total=len(transacciones),
            reconciliadas=conteo[str(Clasificacion.RECONCILIADO)],
            por_clasificacion=dict(conteo),
            monto_total=sum(t.monto_referencia or 0.0 for t in transacciones),
            monto_en_discrepancia=sum(t.diferencia_monto for t in transacciones),
        )
