"""Las reglas de clasificacion, una clase cada una.

Todas tienen la misma forma, asi que el motor solo las recorre en orden sin saber
que hace ninguna. Cambiar un criterio de negocio manana es tocar una clase, no el
motor.

El orden importa: `ReglaReconciliado` va de ultima porque `RECONCILIADO` es la
unica etiqueta excluyente y solo puede aplicar si ninguna otra encontro nada.

Un par de hallazgos —el desfase de fechas y el banco distinto entre fuentes— los
dejo como observacion y no como etiqueta: el enunciado no define ninguna para
esos casos y no me parecio bien inventarme vocabulario que nadie acordo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta

from reconciliacion.dominio.enums import Clasificacion
from reconciliacion.dominio.modelos import ESTADO_OK_SQLITE
from reconciliacion.dominio.transaccion import TransaccionReconciliada

#: Tolerancia admitida al comparar las fechas de las distintas fuentes.
TOLERANCIA_FECHAS = timedelta(hours=2)


def formatear_monto(valor: float | None) -> str:
    """Formatea un monto con separador de miles colombiano.

    Args:
        valor: Monto a formatear.

    Returns:
        El monto como texto (por ejemplo ``225.000``), o ``sin dato`` si es
        `None`.
    """
    if valor is None:
        return "sin dato"
    return f"{valor:,.0f}".replace(",", ".")


class ReglaClasificacion(ABC):
    """Contrato de una regla de clasificacion."""

    @abstractmethod
    def aplicar(self, transaccion: TransaccionReconciliada) -> None:
        """Evalua la transaccion y le agrega etiquetas u observaciones.

        Args:
            transaccion: Transaccion a evaluar, modificada en sitio.
        """


class ReglaPresencia(ReglaClasificacion):
    """Detecta en que fuentes falta la transaccion.

    Cubre las tres etiquetas de faltante del enunciado y ademas las
    combinaciones que este no nombra (por ejemplo, presente solo en el CSV),
    de modo que **ninguna transaccion del universo quede sin clasificar**:

    * sin CSV y sin SQLite -> `NO_AUTORIZADO` (el banco reporta algo que nadie
      autorizo ni contabilizo)
    * sin CSV pero con SQLite -> `NO_AUTORIZADO`, porque la autorizacion es la
      que da legitimidad a la operacion
    * sin SQLite -> `NO_CONTABILIZADO`
    * sin JSON -> `NO_ENCONTRADO_EN_JSON`
    """

    def aplicar(self, transaccion: TransaccionReconciliada) -> None:
        """Agrega las etiquetas de faltante que correspondan."""
        if not transaccion.presente_csv:
            movimiento = transaccion.movimiento
            detalle = f" (movimiento {movimiento.id_movimiento})" if movimiento else ""
            transaccion.agregar(
                Clasificacion.NO_AUTORIZADO,
                f"El banco reporta la transaccion{detalle} pero no existe autorizacion en el CSV.",
            )

        if not transaccion.presente_sqlite and transaccion.presente_csv:
            transaccion.agregar(
                Clasificacion.NO_CONTABILIZADO,
                "Autorizada pero sin registro contable en SQLite.",
            )

        if not transaccion.presente_json and transaccion.presente_csv:
            transaccion.agregar(
                Clasificacion.NO_ENCONTRADO_EN_JSON,
                "Autorizada pero sin movimiento bancario: no llego al banco.",
            )


class ReglaMonto(ReglaClasificacion):
    """Detecta diferencias de monto entre las fuentes presentes."""

    def aplicar(self, transaccion: TransaccionReconciliada) -> None:
        """Agrega `DISCREPANCIA_MONTO` si los montos no son identicos."""
        if not transaccion.hay_discrepancia_monto:
            return

        partes = []
        if transaccion.monto_csv is not None:
            partes.append(f"CSV {formatear_monto(transaccion.monto_csv)}")
        if transaccion.monto_sqlite is not None:
            partes.append(f"SQLite {formatear_monto(transaccion.monto_sqlite)}")
        if transaccion.monto_json is not None:
            partes.append(f"JSON {formatear_monto(transaccion.monto_json)}")

        transaccion.agregar(
            Clasificacion.DISCREPANCIA_MONTO,
            f"Monto {' vs '.join(partes)} (dif. {formatear_monto(transaccion.diferencia_monto)}).",
        )


class ReglaEstado(ReglaClasificacion):
    """Detecta transacciones que la contabilidad no dio por buenas.

    Cada fuente usa su propio vocabulario (`AUTORIZADO`, `CONTABILIZADO`,
    `COMPLETADO`) y los tres representan el mismo estado "OK", asi que la sola
    diferencia de textos **no** es una discrepancia. Solo cuenta el estado de
    SQLite cuando es `PENDIENTE` o `RECHAZADO`.
    """

    def aplicar(self, transaccion: TransaccionReconciliada) -> None:
        """Agrega `DISCREPANCIA_ESTADO` si el estado contable no es OK."""
        contabilizacion = transaccion.contabilizacion
        if contabilizacion is None or contabilizacion.estado == ESTADO_OK_SQLITE:
            return

        transaccion.agregar(
            Clasificacion.DISCREPANCIA_ESTADO,
            f"Estado SQLite {contabilizacion.estado} "
            f"(CSV {transaccion.estado_csv or 'sin dato'}, "
            f"JSON {transaccion.estado_json or 'sin dato'}).",
        )


class ReglaFechas(ReglaClasificacion):
    """Comprueba que las fechas de las fuentes esten dentro de la tolerancia.

    El enunciado pide comparar fechas con tolerancia de +-2 horas pero no
    define una etiqueta para el desfase, asi que el hallazgo se deja como
    observacion: queda documentado en el reporte sin inventar una etiqueta que
    no esta en el vocabulario acordado.
    """

    def aplicar(self, transaccion: TransaccionReconciliada) -> None:
        """Agrega una observacion si las fechas se separan mas de la tolerancia."""
        fechas = transaccion.fechas_presentes
        if len(fechas) < 2:
            return

        desfase = max(fechas) - min(fechas)
        if desfase > TOLERANCIA_FECHAS:
            horas = desfase.total_seconds() / 3600
            transaccion.observaciones.append(
                f"Fechas con desfase de {horas:.1f} h entre fuentes (tolerancia 2 h)."
            )


class ReglaBanco(ReglaClasificacion):
    """Comprueba que las fuentes coincidan en la entidad bancaria.

    El reporte trae una sola columna `Banco` porque las tres fuentes deberian
    reportar el mismo, y la transaccion toma el de la primera fuente
    disponible. Si no coincidieran, esa columna estaria escondiendo un
    problema, asi que se verifica y se deja constancia.

    Igual que con las fechas, el hallazgo va como observacion y no como
    etiqueta: el enunciado no define una para este caso y prefiero no inventar
    vocabulario.
    """

    def aplicar(self, transaccion: TransaccionReconciliada) -> None:
        """Agrega una observacion si las fuentes reportan bancos distintos."""
        bancos = {
            origen: banco
            for origen, banco in (
                ("CSV", transaccion.autorizacion.banco if transaccion.autorizacion else None),
                (
                    "SQLite",
                    transaccion.contabilizacion.banco if transaccion.contabilizacion else None,
                ),
                ("JSON", transaccion.movimiento.banco if transaccion.movimiento else None),
            )
            if banco
        }
        if len(set(bancos.values())) > 1:
            detalle = ", ".join(f"{origen} {banco}" for origen, banco in bancos.items())
            transaccion.observaciones.append(f"Banco distinto entre fuentes ({detalle}).")


class ReglaReconciliado(ReglaClasificacion):
    """Marca como `RECONCILIADO` lo que quedo sin ningun hallazgo.

    Debe ejecutarse de ultima: `RECONCILIADO` es la unica etiqueta excluyente
    y exige presencia en las tres fuentes, montos identicos y estado contable
    en `CONTABILIZADO`.
    """

    def aplicar(self, transaccion: TransaccionReconciliada) -> None:
        """Agrega `RECONCILIADO` si no hay etiquetas previas y todo cuadra."""
        if transaccion.clasificaciones:
            return

        completa = transaccion.fuentes_presentes == 3
        estado_ok = (
            transaccion.contabilizacion is not None
            and transaccion.contabilizacion.estado == ESTADO_OK_SQLITE
        )
        if completa and estado_ok and not transaccion.hay_discrepancia_monto:
            transaccion.agregar(Clasificacion.RECONCILIADO)


#: Reglas en el orden en que deben aplicarse.
REGLAS_POR_DEFECTO: tuple[ReglaClasificacion, ...] = (
    ReglaPresencia(),
    ReglaMonto(),
    ReglaEstado(),
    ReglaFechas(),
    ReglaBanco(),
    ReglaReconciliado(),
)
