"""Una clase por cada cosa del negocio.

Preferi un modelo por fuente antes que diccionarios genericos: asi el editor me
avisa si me equivoco de campo y cualquiera que abra el codigo sabe que trae cada
archivo sin ir a mirarlo.

`FilaAutorizacionCruda` merece explicacion aparte: es la fila del CSV tal como
esta en disco, con sus campos rotos y todo. Existe para separar *leer* de
*limpiar* —el cargador no interpreta nada y el parser no toca el disco—. Gracias
a eso el parseo del JSON malformado se prueba pasandole un string, sin archivos
de por medio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

# Vocabulario de estado de cada fuente. Los tres representan el mismo estado
# "OK" y por si solos NO constituyen una discrepancia (regla explicita del
# enunciado): AUTORIZADO == CONTABILIZADO == COMPLETADO.
ESTADO_OK_CSV = "AUTORIZADO"
ESTADO_OK_SQLITE = "CONTABILIZADO"
ESTADO_OK_JSON = "COMPLETADO"

ESTADOS_EQUIVALENTES_OK = frozenset({ESTADO_OK_CSV, ESTADO_OK_SQLITE, ESTADO_OK_JSON})

# Vocabulario admitido por fuente. Un estado fuera de estas listas no es una
# discrepancia de negocio sino un problema de integridad del dato: significa
# que la fuente trae un valor que el sistema no sabe interpretar. Se reporta
# como advertencia al cargar, sin descartar el registro.
ESTADOS_VALIDOS_CSV = frozenset({ESTADO_OK_CSV})
ESTADOS_VALIDOS_SQLITE = frozenset({ESTADO_OK_SQLITE, "PENDIENTE", "RECHAZADO"})
ESTADOS_VALIDOS_JSON = frozenset({ESTADO_OK_JSON})

# Entidades de retencion que pueden aparecer en el CSV. `cree` y `aumento` se
# parsean para no confundirlas con las demas, pero no suman en ninguna columna.
ENTIDADES_RETENCION = frozenset({"iva", "ica", "fuente", "cree", "aumento"})


@dataclass(frozen=True)
class Retencion:
    """Una retencion practicada sobre la transaccion.

    Attributes:
        entidad: Entidad de la retencion (`iva`, `ica`, `fuente`, `cree`,
            `aumento`).
        monto: Valor de la retencion. Viene negativo en la fuente y se
            conserva con su signo, sin convertir a positivo.
    """

    entidad: str
    monto: float


@dataclass(frozen=True)
class FilaAutorizacionCruda:
    """Fila del CSV tal cual viene en disco, sin interpretar.

    Los campos `monto_crudo` y `marca_cruda` contienen estructuras tipo JSON
    deliberadamente malformadas; su limpieza es responsabilidad del paquete
    `limpieza`, no del loader.

    Attributes:
        id_transaccion: Identificador `TRXxxxx`.
        monto_crudo: Campo `Monto` sin parsear.
        fecha_cruda: Campo `Fecha` sin parsear.
        banco: Entidad bancaria.
        marca_cruda: Campo `Marca` sin parsear (trae retenciones + marca).
        estado: Estado segun el CSV (siempre `AUTORIZADO`).
        numero_fila: Numero de fila en el archivo, para trazar errores.
    """

    id_transaccion: str
    monto_crudo: str
    fecha_cruda: str
    banco: str
    marca_cruda: str
    estado: str
    numero_fila: int


@dataclass(frozen=True)
class Autorizacion:
    """Transaccion autorizada, ya limpia (origen: CSV).

    Attributes:
        id_transaccion: Identificador `TRXxxxx`.
        monto: Monto extraido del campo malformado.
        fecha: Fecha y hora de autorizacion.
        banco: Entidad bancaria.
        marca: Nombre de la marca extraido del campo malformado.
        estado: Estado segun el CSV.
        retenciones: Retenciones halladas en la fila (entre 1 y 4).
    """

    id_transaccion: str
    monto: Optional[float]
    fecha: Optional[datetime]
    banco: str
    marca: Optional[str]
    estado: str
    retenciones: List[Retencion] = field(default_factory=list)

    def total_retencion(self, *entidades: str) -> float:
        """Suma las retenciones de las entidades indicadas.

        Una entidad ausente aporta 0 y una entidad repetida suma todas sus
        ocurrencias, tal como exige el enunciado.

        Args:
            *entidades: Entidades a sumar, por ejemplo `"iva", "ica"`.

        Returns:
            La suma (normalmente negativa) de las retenciones solicitadas.
        """
        buscadas = {e.lower() for e in entidades}
        return sum(r.monto for r in self.retenciones if r.entidad in buscadas)


@dataclass(frozen=True)
class Contabilizacion:
    """Registro contable de la transaccion (origen: SQLite).

    Unica fuente que aporta `centro_costo` y unica cuyo estado puede ser
    `PENDIENTE` o `RECHAZADO`.

    Attributes:
        id_transaccion: Identificador `TRXxxxx` (columna `Referencia`).
        monto: Monto contabilizado.
        fecha: Fecha y hora del asiento.
        centro_costo: Centro de costo asociado.
        estado: `CONTABILIZADO`, `PENDIENTE` o `RECHAZADO`.
        banco: Entidad bancaria.
        marca: Marca segun la contabilidad.
    """

    id_transaccion: str
    monto: Optional[float]
    fecha: Optional[datetime]
    centro_costo: str
    estado: str
    banco: Optional[str]
    marca: Optional[str]

    @property
    def estado_es_ok(self) -> bool:
        """Indica si el estado contable equivale al estado "OK"."""
        return self.estado == ESTADO_OK_SQLITE


@dataclass(frozen=True)
class MovimientoBancario:
    """Movimiento reportado por el banco (origen: JSON).

    Attributes:
        id_movimiento: Identificador propio del movimiento (`MOVxxxx`).
        id_transaccion: Referencia a la transaccion (`TRXxxxx`).
        monto: Monto reportado por el banco.
        fecha: Fecha y hora del movimiento.
        banco: Entidad bancaria.
        estado: Estado segun el banco (siempre `COMPLETADO`).
        marca: Marca segun el banco.
    """

    id_movimiento: str
    id_transaccion: str
    monto: Optional[float]
    fecha: Optional[datetime]
    banco: Optional[str]
    estado: str
    marca: Optional[str]
