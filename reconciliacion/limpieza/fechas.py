"""Fechas, que cada fuente escribe a su manera.

    CSV y SQLite    26/07/2026 9:00
    JSON            2026-07-26 09:00:00

Pruebo varios formatos en orden en vez de asumir uno solo. Y si ninguno encaja
devuelvo `None` en lugar de reventar: prefiero la fila con un hueco y una
advertencia antes que perderla.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

#: Formatos aceptados, del mas probable al menos probable.
FORMATOS_FECHA: Sequence[str] = (
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y",
    "%Y-%m-%d",
)


def parsear_fecha(valor: object) -> Optional[datetime]:
    """Convierte un valor de fecha a `datetime` probando los formatos conocidos.

    Args:
        valor: Texto (o `datetime` ya parseado) proveniente de cualquier fuente.

    Returns:
        El `datetime` correspondiente, o `None` si el valor esta vacio o no
        coincide con ningun formato conocido. Devolver `None` en vez de lanzar
        permite que la fila se conserve y quede reportada como incidencia, en
        lugar de perderse en silencio.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor

    texto = str(valor).strip()
    if not texto:
        return None

    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None
