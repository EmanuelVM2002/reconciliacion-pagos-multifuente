"""Sacar el monto del campo `Monto`, que no es un numero.

Lo que hay ahi es una estructura tipo JSON reventada a proposito. Intente primero
repararla para poder usar `json.loads()` y lo abandone: conviven varias formas de
corrupcion y cualquier arreglo generico se rompe con alguna. Al final voy directo
a buscar la clave con una expresion regular tolerante y me da igual como este
escapado lo de alrededor.

Dos cosas que me costaron:

1. El monto viene escrito de tres maneras: `1250000`, `"188.000 COP"` y
   `"$175.000,00"`. La tercera es formato colombiano —el punto separa miles y la
   coma los decimales— y si uno lee el punto como decimal, `$175.000,00` se
   convierte en 17.500.000 y aparecen 53 discrepancias que no existen.
2. La clave `monto` puede estar dos veces en la misma fila con valores distintos.
   Aplique lo que hace cualquier parser de JSON: gana la ultima. Pasa una sola vez
   en el archivo y el valor que gana es el que confirman SQLite y el banco, asi
   que la regla es la correcta.
"""

from __future__ import annotations

import re
from typing import List, Optional

#: Captura el valor de la clave `monto`, este entrecomillado o no y traiga o no
#: escapes sobrantes antes de los dos puntos.
_PATRON_MONTO = re.compile(
    r"monto\\*\"?\s*\\*\"?\s*:\s*(\"[^\"]*\"|-?[\d.,]+)",
    re.IGNORECASE,
)

#: Numero escrito con punto como separador de miles: 410.000 / 1.720.000
_PATRON_MILES = re.compile(r"^-?\d{1,3}(\.\d{3})+$")

#: Caracteres de moneda y ruido a descartar antes de convertir.
_RUIDO = str.maketrans("", "", "$  ")


def normalizar_valor_monetario(texto: str) -> Optional[float]:
    """Convierte a `float` un monto escrito en cualquiera de los formatos vistos.

    Args:
        texto: Valor tal como aparece en la fuente, por ejemplo ``1250000``,
            ``"188.000 COP"`` o ``"$175.000,00"``.

    Returns:
        El valor numerico, o `None` si el texto no representa un numero.

    Examples:
        >>> normalizar_valor_monetario('1250000')
        1250000.0
        >>> normalizar_valor_monetario('"188.000 COP"')
        188000.0
        >>> normalizar_valor_monetario('"$175.000,00"')
        175000.0
    """
    if texto is None:
        return None

    limpio = texto.strip().strip('"').replace("\\", "")
    limpio = re.sub(r"(?i)\b(COP|USD)\b", "", limpio)
    limpio = limpio.translate(_RUIDO).strip()
    if not limpio:
        return None

    if "," in limpio:
        # Formato colombiano: el punto separa miles y la coma, decimales.
        limpio = limpio.replace(".", "").replace(",", ".")
    elif _PATRON_MILES.match(limpio):
        # Solo puntos y en grupos de tres: son separadores de miles.
        limpio = limpio.replace(".", "")

    try:
        return float(limpio)
    except ValueError:
        return None


def extraer_montos(campo_crudo: str) -> List[float]:
    """Devuelve todos los montos hallados en el campo, en orden de aparicion.

    Sirve para auditar las filas con la clave `monto` repetida.

    Args:
        campo_crudo: Contenido completo del campo `Monto` del CSV.

    Returns:
        Los valores encontrados; lista vacia si no hay ninguno.
    """
    valores: List[float] = []
    for bruto in _PATRON_MONTO.findall(campo_crudo or ""):
        valor = normalizar_valor_monetario(bruto)
        if valor is not None:
            valores.append(valor)
    return valores


def extraer_monto(campo_crudo: str) -> Optional[float]:
    """Extrae el monto vigente del campo malformado del CSV.

    Si la clave `monto` aparece varias veces se conserva la **ultima**, que es
    la semantica estandar de JSON ante claves duplicadas.

    Args:
        campo_crudo: Contenido completo del campo `Monto` del CSV.

    Returns:
        El monto de la transaccion, o `None` si no se pudo extraer.
    """
    valores = extraer_montos(campo_crudo)
    return valores[-1] if valores else None
