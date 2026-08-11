"""Extraccion y normalizacion del nombre de la marca.

En el CSV la marca no viene en un campo propio: viaja como ultimo elemento de
la lista de retenciones (`{"marca": "AMERICAN EAGLE"}`), dentro de la misma
estructura malformada. Se extrae con una expresion regular tolerante a los
escapes sobrantes, igual que el monto.

Regla de normalizacion (decision documentada)
---------------------------------------------
Las tres fuentes **no escriben la marca igual**: el CSV guarda el nombre
comercial completo y SQLite y el banco guardan solo su **primera palabra**.

===================  ==========  ==========
CSV                  SQLite      JSON
===================  ==========  ==========
``NAF NAF``          ``NAF``     ``NAF``
``AMERICAN EAGLE``   ``AMERICAN````AMERICAN``
``AMERICANINO``      ``AMERICANINO``  ``AMERICANINO``
``CHEVIGNON``        ``CHEVIGNON``    ``CHEVIGNON``
``RIFLE``            ``RIFLE``        ``RIFLE``
===================  ==========  ==========

Por eso la normalizacion es: mayusculas, sin tildes, sin puntuacion, espacios
colapsados y **se conserva solo el primer token**. Comparar literalmente
produciria 166 falsos negativos sobre 500 filas (un tercio del archivo), todos
de las marcas ``NAF NAF`` y ``AMERICAN EAGLE``.

Se eligio el primer token, y no un recorte por prefijo comun, porque es una
regla estable y explicable: el catalogo de marcas no tiene dos nombres que
compartan la primera palabra (``AMERICANINO`` y ``AMERICAN EAGLE`` normalizan
a ``AMERICANINO`` y ``AMERICAN``, que siguen siendo distintos), asi que no
introduce colisiones.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional

#: Captura el valor de la clave `marca`, tolerando escapes sobrantes.
_PATRON_MARCA = re.compile(
    r"marca\\*\"?\s*\\*\"?\s*:\s*\\*\"\s*([^\"\\]+?)\s*\\*\"",
    re.IGNORECASE,
)

_PATRON_NO_ALFANUMERICO = re.compile(r"[^A-Z0-9 ]+")
_PATRON_ESPACIOS = re.compile(r"\s+")


def extraer_marca(campo_crudo: str) -> Optional[str]:
    """Extrae el nombre de la marca del campo malformado del CSV.

    Args:
        campo_crudo: Contenido completo del campo `Marca` del CSV, que incluye
            la lista de retenciones y, al final, la marca.

    Returns:
        El nombre de la marca tal como aparece en el archivo, o `None` si no
        se encontro.

    Examples:
        >>> extraer_marca('[{"financial_entity": "iva"}, {"marca": "NAF NAF"}}]')
        'NAF NAF'
    """
    if not campo_crudo:
        return None
    coincidencias = _PATRON_MARCA.findall(campo_crudo)
    if not coincidencias:
        return None
    # Se toma la ultima por coherencia con la regla aplicada al monto.
    return coincidencias[-1].strip() or None


def normalizar_marca(marca: Optional[str]) -> Optional[str]:
    """Lleva un nombre de marca a la forma canonica de comparacion.

    Aplica: mayusculas, eliminacion de tildes y puntuacion, colapso de
    espacios y recorte al primer token (ver la nota de modulo).

    Args:
        marca: Nombre de la marca segun cualquiera de las fuentes.

    Returns:
        La forma normalizada, o `None` si la entrada es vacia.

    Examples:
        >>> normalizar_marca('NAF NAF')
        'NAF'
        >>> normalizar_marca('American Eagle')
        'AMERICAN'
        >>> normalizar_marca('AMERICANINO')
        'AMERICANINO'
    """
    if not marca:
        return None

    sin_tildes = "".join(
        caracter
        for caracter in unicodedata.normalize("NFKD", str(marca))
        if not unicodedata.combining(caracter)
    )
    limpia = _PATRON_NO_ALFANUMERICO.sub(" ", sin_tildes.upper())
    limpia = _PATRON_ESPACIOS.sub(" ", limpia).strip()
    if not limpia:
        return None
    return limpia.split(" ")[0]


def marcas_coinciden(*marcas: Optional[str]) -> Optional[bool]:
    """Indica si las marcas de las fuentes presentes son la misma.

    Args:
        *marcas: Marca segun cada fuente. Los valores `None` (fuente ausente o
            sin marca) se ignoran.

    Returns:
        `True` si todas las marcas presentes normalizan al mismo valor,
        `False` si difieren, y `None` si no hay al menos una marca con la cual
        comparar.
    """
    normalizadas = {n for n in (normalizar_marca(m) for m in marcas) if n}
    if not normalizadas:
        return None
    return len(normalizadas) == 1


def primera_no_vacia(valores: Iterable[Optional[str]]) -> Optional[str]:
    """Devuelve el primer valor no vacio de una secuencia.

    Args:
        valores: Candidatos en orden de preferencia.

    Returns:
        El primer valor con contenido, o `None` si todos estan vacios.
    """
    for valor in valores:
        if valor:
            return valor
    return None
