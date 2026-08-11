"""Avisos de avance dentro de las etapas largas.

Limpiar 500 filas o escribir 505 de Excel toma lo suficiente como para que una
interfaz que solo se entera al terminar cada etapa parezca colgada. Por eso las
funciones largas aceptan una funcion a la que le avisan cada tantos elementos.

Lo importante: el negocio no sabe nada de hilos ni de ventanas, solo avisa. Quien
lo llame decide que hacer con el aviso —la terminal lo ignora, la ventana mueve
la barra—.
"""

from __future__ import annotations

from typing import Callable, Optional

#: Firma del aviso de avance parcial: (elementos procesados, total).
ProgresoParcial = Callable[[int, int], None]

#: Cada cuantos elementos se avisa por defecto.
LOTE_POR_DEFECTO = 20


def notificar(
    progreso: Optional[ProgresoParcial],
    procesados: int,
    total: int,
    cada: int = LOTE_POR_DEFECTO,
) -> None:
    """Avisa del avance cada cierto numero de elementos.

    Avisar en cada elemento seria costoso y avisar solo al final no sirve de
    nada, asi que se reporta por lotes y siempre en el ultimo elemento, para
    que el avance cierre exacto.

    Args:
        progreso: Funcion a la que avisar. Si es `None` no se hace nada.
        procesados: Elementos ya procesados.
        total: Total de elementos de la etapa.
        cada: Tamano del lote entre avisos.
    """
    if progreso is None:
        return
    if procesados % cada == 0 or procesados == total:
        progreso(procesados, total)
