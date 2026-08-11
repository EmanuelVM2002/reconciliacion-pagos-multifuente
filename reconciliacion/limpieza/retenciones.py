"""Las retenciones, que estan metidas donde mismo que la marca.

Reglas del archivo, todas contempladas aqui:

* entre 1 y 4 por fila, de `iva`, `ica`, `fuente`, `cree` o `aumento`;
* la que no aparece vale 0;
* una misma entidad puede repetirse con montos distintos —pasa en 267 de las 500
  filas—, asi que hay que sumar todas sus ocurrencias. Quien parsee a un
  diccionario simple pierde valores y ni se entera;
* vienen en negativo y asi se quedan;
* `cree` y `aumento` se leen para no confundirlas con las demas, pero no suman en
  ninguna de las tres columnas del reporte.

La expresion regular empareja la entidad con el monto *del mismo objeto*, para no
cruzar la entidad de una retencion con el monto de la siguiente.
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
