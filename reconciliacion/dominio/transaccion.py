"""La transaccion vista desde las tres fuentes a la vez.

Es una fila del reporte final: junta la version autorizada, la contabilizada y la
bancaria, y calcula lo que el resto del sistema necesita —en que fuentes esta,
monto de referencia, diferencia, fecha, banco—.

El criterio para decidir que va aqui: lo que se puede responder mirando *una*
transaccion vive en esta clase; lo que necesita mirar *todas* (el umbral de
fraude, el patron de repeticion) vive en el detector.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence

from reconciliacion.dominio.enums import Clasificacion, NivelRiesgo, TipoFraude
from reconciliacion.dominio.modelos import Autorizacion, Contabilizacion, MovimientoBancario


@dataclass
class TransaccionReconciliada:
    """Una transaccion vista desde las tres fuentes.

    Attributes:
        id_transaccion: Llave de cruce `TRXxxxx`.
        autorizacion: Version del CSV, o `None` si no esta en esa fuente.
        contabilizacion: Version de SQLite, o `None`.
        movimiento: Version del JSON, o `None`.
        clasificaciones: Etiquetas asignadas por el reconciliador.
        tipos_fraude: Patrones de fraude detectados.
        observaciones: Explicaciones legibles de cada hallazgo.
    """

    id_transaccion: str
    autorizacion: Optional[Autorizacion] = None
    contabilizacion: Optional[Contabilizacion] = None
    movimiento: Optional[MovimientoBancario] = None
    clasificaciones: List[Clasificacion] = field(default_factory=list)
    tipos_fraude: List[TipoFraude] = field(default_factory=list)
    observaciones: List[str] = field(default_factory=list)

    # --- Presencia por fuente --------------------------------------------

    @property
    def presente_csv(self) -> bool:
        """Indica si la transaccion fue autorizada (esta en el CSV)."""
        return self.autorizacion is not None

    @property
    def presente_sqlite(self) -> bool:
        """Indica si la transaccion fue contabilizada (esta en SQLite)."""
        return self.contabilizacion is not None

    @property
    def presente_json(self) -> bool:
        """Indica si la transaccion llego al banco (esta en el JSON)."""
        return self.movimiento is not None

    @property
    def fuentes_presentes(self) -> int:
        """Cuenta en cuantas de las tres fuentes aparece la transaccion."""
        return sum((self.presente_csv, self.presente_sqlite, self.presente_json))

    # --- Montos -----------------------------------------------------------

    @property
    def monto_csv(self) -> Optional[float]:
        """Monto extraido del CSV."""
        return self.autorizacion.monto if self.autorizacion else None

    @property
    def monto_sqlite(self) -> Optional[float]:
        """Monto segun la contabilidad."""
        return self.contabilizacion.monto if self.contabilizacion else None

    @property
    def monto_json(self) -> Optional[float]:
        """Monto segun el banco."""
        return self.movimiento.monto if self.movimiento else None

    @property
    def montos_presentes(self) -> List[float]:
        """Montos disponibles entre las fuentes presentes."""
        return [m for m in (self.monto_csv, self.monto_sqlite, self.monto_json) if m is not None]

    @property
    def monto_referencia(self) -> Optional[float]:
        """Monto que representa a la transaccion.

        Es el valor que coincide en la mayoria de las fuentes presentes; si hay
        empate se toma el mayor, por criterio conservador (se prefiere
        sobreestimar la exposicion antes que subestimarla). Se usa tanto para
        el umbral de 3 sigma como para la comparacion de patron.

        Returns:
            El monto de referencia, o `None` si ninguna fuente aporta monto.
        """
        montos = self.montos_presentes
        if not montos:
            return None
        conteo = Counter(montos)
        maximo = max(conteo.values())
        return max(monto for monto, veces in conteo.items() if veces == maximo)

    @property
    def diferencia_monto(self) -> float:
        """Diferencia entre el mayor y el menor monto de las fuentes presentes.

        Returns:
            `0.0` si todas coinciden o si no hay montos con que comparar.
        """
        montos = self.montos_presentes
        if len(montos) < 2:
            return 0.0
        return max(montos) - min(montos)

    @property
    def hay_discrepancia_monto(self) -> bool:
        """Indica si los montos de las fuentes presentes no son identicos."""
        return len(set(self.montos_presentes)) > 1

    # --- Fechas, banco y marca -------------------------------------------

    @property
    def fecha_csv(self) -> Optional[datetime]:
        """Fecha de autorizacion."""
        return self.autorizacion.fecha if self.autorizacion else None

    @property
    def fecha_sqlite(self) -> Optional[datetime]:
        """Fecha del asiento contable."""
        return self.contabilizacion.fecha if self.contabilizacion else None

    @property
    def fecha_json(self) -> Optional[datetime]:
        """Fecha del movimiento bancario."""
        return self.movimiento.fecha if self.movimiento else None

    @property
    def fechas_presentes(self) -> List[datetime]:
        """Fechas disponibles entre las fuentes presentes."""
        return [f for f in (self.fecha_csv, self.fecha_sqlite, self.fecha_json) if f is not None]

    @property
    def fecha_referencia(self) -> Optional[datetime]:
        """Fecha que representa a la transaccion.

        Se toma la primera disponible en el orden CSV -> SQLite -> JSON. El
        criterio es de negocio: la autorizacion es el momento en que la
        operacion realmente ocurre; la contabilizacion y el movimiento
        bancario son ecos posteriores de ese hecho. Es la fecha que se usa
        para el fraude por hora inusual y por patron.

        Returns:
            La fecha de referencia, o `None` si ninguna fuente la aporta.
        """
        for fecha in (self.fecha_csv, self.fecha_sqlite, self.fecha_json):
            if fecha is not None:
                return fecha
        return None

    @property
    def banco(self) -> Optional[str]:
        """Entidad bancaria, tomada de la primera fuente que la reporte."""
        candidatos: Sequence[Optional[str]] = (
            self.autorizacion.banco if self.autorizacion else None,
            self.contabilizacion.banco if self.contabilizacion else None,
            self.movimiento.banco if self.movimiento else None,
        )
        for banco in candidatos:
            if banco:
                return banco
        return None

    @property
    def marca_csv(self) -> Optional[str]:
        """Marca extraida del CSV."""
        return self.autorizacion.marca if self.autorizacion else None

    @property
    def marca_sqlite(self) -> Optional[str]:
        """Marca segun la contabilidad."""
        return self.contabilizacion.marca if self.contabilizacion else None

    @property
    def marca_json(self) -> Optional[str]:
        """Marca segun el banco."""
        return self.movimiento.marca if self.movimiento else None

    # --- Estados ----------------------------------------------------------

    @property
    def estado_csv(self) -> Optional[str]:
        """Estado segun el CSV (siempre `AUTORIZADO` cuando esta presente)."""
        return self.autorizacion.estado if self.autorizacion else None

    @property
    def estado_sqlite(self) -> Optional[str]:
        """Estado contable: `CONTABILIZADO`, `PENDIENTE` o `RECHAZADO`."""
        return self.contabilizacion.estado if self.contabilizacion else None

    @property
    def estado_json(self) -> Optional[str]:
        """Estado segun el banco (siempre `COMPLETADO` cuando esta presente)."""
        return self.movimiento.estado if self.movimiento else None

    # --- Resultado --------------------------------------------------------

    @property
    def es_fraude(self) -> bool:
        """Indica si se detecto al menos un patron de fraude."""
        return bool(self.tipos_fraude)

    @property
    def nivel_riesgo(self) -> Optional[NivelRiesgo]:
        """Nivel de riesgo mas alto entre los fraudes detectados.

        Returns:
            El nivel correspondiente, o `None` si la transaccion no es fraude.
        """
        from reconciliacion.dominio.enums import ORDEN_SEVERIDAD, PRIORIDAD_RIESGO

        if not self.tipos_fraude:
            return None
        niveles = {PRIORIDAD_RIESGO[tipo] for tipo in self.tipos_fraude}
        for nivel in ORDEN_SEVERIDAD:
            if nivel in niveles:
                return nivel
        return None

    @property
    def esta_reconciliada(self) -> bool:
        """Indica si la transaccion quedo sin ningun hallazgo de reconciliacion."""
        return self.clasificaciones == [Clasificacion.RECONCILIADO]

    def agregar(self, clasificacion: Clasificacion, observacion: str = "") -> None:
        """Asigna una etiqueta a la transaccion, evitando duplicados.

        Args:
            clasificacion: Etiqueta a agregar.
            observacion: Texto legible que explica el hallazgo.
        """
        if clasificacion not in self.clasificaciones:
            self.clasificaciones.append(clasificacion)
        if observacion:
            self.observaciones.append(observacion)
