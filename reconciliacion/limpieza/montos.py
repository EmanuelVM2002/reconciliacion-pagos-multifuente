"""Extraccion del monto desde el campo `Monto` del CSV.

El campo no es un numero: es una estructura tipo JSON **deliberadamente
malformada** (comillas desbalanceadas, llaves de mas, claves con escapes
sobrantes) dentro de la cual viene la clave `monto`. Un `json.loads()` directo
falla en las 500 filas del archivo.

Estrategia
----------
En vez de intentar *reparar* el JSON (fragil: hay mas de una variante de
corrupcion conviviendo), se extrae el dato con una expresion regular tolerante
que busca la clave `monto` sin importar como venga escapada. Es robusto ante
cualquier corrupcion que no toque la clave ni su valor.

Dos particularidades del archivo, ambas contempladas aqui:

1. **El valor viene en tres formatos distintos**:
   ``1250000`` (numero puro), ``"188.000 COP"`` (miles con punto) y
   ``"$175.000,00"`` (formato colombiano: punto = miles, coma = decimales).
   Interpretar el tercero como si el punto fuera decimal convierte
   ``$175.000,00`` en 17.500.000 y fabrica discrepancias que no existen.

2. **La clave `monto` puede aparecer repetida en la misma fila** y con valores
   distintos. Se aplica la semantica estandar de JSON: **gana la ultima
   ocurrencia**. Es el criterio que coincide con lo que reportan SQLite y el
   banco para esa transaccion.
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
