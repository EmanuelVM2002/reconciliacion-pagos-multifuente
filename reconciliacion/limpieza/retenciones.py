"""Extraccion de las retenciones practicadas, desde el campo `Marca` del CSV.

Cada fila trae entre 1 y 4 retenciones, cada una con su entidad
(`financial_entity`) y su valor (`amount`), dentro de la misma estructura
malformada de la que sale la marca.

Particularidades del archivo, todas contempladas aqui:

* Las entidades posibles son `iva`, `ica`, `fuente`, `cree` y `aumento`, y no
  todas aparecen en todas las filas. **Una entidad ausente vale 0.**
* **Una misma entidad puede repetirse** en la fila con montos distintos; en ese
  caso se suman todas sus ocurrencias.
* Los valores vienen **negativos** y se conservan con su signo.
* `cree` y `aumento` se parsean para no confundirlas con las demas, pero no
  entran en ninguna de las tres columnas de salida.

Se extrae con una expresion regular que empareja entidad y monto dentro del
mismo objeto, en vez de parsear el JSON: el campo trae al menos seis variantes
de corrupcion conviviendo (aperturas ``[{``, ``{{`` o ``({``, cierres
``}}]""`` o ``})"``, claves con escapes sobrantes como ``"monto\\":`` y claves
duplicadas y pegadas como ``financial_entityfinancial_entity"``), asi que
cualquier intento de reparacion generica se rompe con alguna de ellas.
"""

from __future__ import annotations

import re
from typing import Dict, List

from reconciliacion.dominio.modelos import ENTIDADES_RETENCION, Retencion

#: Empareja `financial_entity` con el `amount` que le sigue dentro del mismo
#: objeto. El `[^{}]*?` impide cruzar la frontera de un objeto y aparear la
#: entidad de una retencion con el monto de la siguiente.
_PATRON_RETENCION = re.compile(
    r"financial_entity\\*\"?\s*\\*\"?\s*:\s*\\*\"\s*([A-Za-z_]+)\s*\\*\""
    r"[^{}]*?"
    r"amount\\*\"?\s*\\*\"?\s*:\s*\\*\"?\s*(-?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)


def extraer_retenciones(campo_crudo: str) -> List[Retencion]:
    """Extrae todas las retenciones presentes en el campo malformado.

    Args:
        campo_crudo: Contenido completo del campo `Marca` del CSV.

    Returns:
        Las retenciones halladas, en orden de aparicion y conservando las
        repeticiones de una misma entidad. Lista vacia si no hay ninguna.

    Examples:
        >>> extraer_retenciones('[{"financial_entity": "iva", "amount": "-100.5"}]')
        [Retencion(entidad='iva', monto=-100.5)]
    """
    retenciones: List[Retencion] = []
    for entidad, monto in _PATRON_RETENCION.findall(campo_crudo or ""):
        entidad_normalizada = entidad.strip().lower()
        try:
            valor = float(monto.replace(",", "."))
        except ValueError:
            continue
        retenciones.append(Retencion(entidad=entidad_normalizada, monto=valor))
    return retenciones


def totalizar_por_entidad(retenciones: List[Retencion]) -> Dict[str, float]:
    """Agrupa las retenciones por entidad sumando las ocurrencias repetidas.

    Args:
        retenciones: Retenciones extraidas de una fila.

    Returns:
        Diccionario entidad -> suma de sus montos. Solo incluye las entidades
        presentes; el consumidor debe tratar las ausentes como 0.
    """
    totales: Dict[str, float] = {}
    for retencion in retenciones:
        totales[retencion.entidad] = totales.get(retencion.entidad, 0.0) + retencion.monto
    return totales


def entidades_desconocidas(retenciones: List[Retencion]) -> List[str]:
    """Devuelve las entidades halladas que no estan en el catalogo esperado.

    Sirve como control de calidad del parseo: si aparece una entidad nueva,
    queda registrada como advertencia en vez de perderse en silencio.

    Args:
        retenciones: Retenciones extraidas de una fila.

    Returns:
        Nombres de entidad fuera de `ENTIDADES_RETENCION`, sin repetir.
    """
    return sorted({r.entidad for r in retenciones if r.entidad not in ENTIDADES_RETENCION})
