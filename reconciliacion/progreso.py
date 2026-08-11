"""Reporte de avance parcial dentro de las etapas largas.

Las etapas del proceso no son instantaneas: limpiar 500 filas, cruzar 505
transacciones o escribir 505 filas de Excel toma el tiempo suficiente como
para que una interfaz que solo se entere al terminar cada etapa parezca
congelada.

Por eso las funciones largas aceptan un `ProgresoParcial` opcional al que
avisan cada cierto numero de elementos. Quien las llama decide que hacer con
ese aviso: la terminal lo ignora y la interfaz lo usa para mover la barra y,
de paso, para cederle el turno al hilo que dibuja.

El paquete de negocio no sabe nada de hilos ni de ventanas: solo avisa.
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
