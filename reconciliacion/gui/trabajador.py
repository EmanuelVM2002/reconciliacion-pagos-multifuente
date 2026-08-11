"""Hilo de trabajo que ejecuta la reconciliacion sin congelar la interfaz.

La reconciliacion completa tarda cerca de un segundo con estos datos, pero el
diseno no puede depender de eso: con un archivo diez veces mas grande la
ventana quedaria muerta. Por eso el proceso corre siempre en un hilo aparte y
la interfaz solo lee de una cola.

El hilo publica dos cosas en esa cola:

* el **avance** que le informa el servicio (paso actual y porcentaje);
* las **lineas de log** que emite el codigo de negocio, capturadas con un
  `logging.Handler` propio. Asi la bitacora de la pantalla es exactamente la
  misma que la de la terminal, sin que el codigo de negocio sepa que existe
  una interfaz.
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
import time
from typing import Optional

from reconciliacion.errores import ErrorReconciliacion
from reconciliacion.gui.mensajes import Mensaje, TipoMensaje
from reconciliacion.log import NOMBRE_LOGGER_RAIZ
from reconciliacion.servicio import ServicioReconciliacion

#: Pausa que el hilo de trabajo se toma en cada aviso para que el hilo de la
#: interfaz alcance a leer la cola y repintar. Ver `_informar_progreso`.
PAUSA_CESION_SEGUNDOS = 0.001

#: Cada cuanto el interprete reparte el GIL mientras corre el proceso. Ver `run`.
INTERVALO_CONMUTACION_SEGUNDOS = 0.0005


class ManejadorCola(logging.Handler):
    """Handler de logging que reenvia cada registro a la cola de la interfaz."""

    def __init__(self, cola: "queue.Queue[Mensaje]") -> None:
        """Crea el handler.

        Args:
            cola: Cola compartida con la interfaz.
        """
        super().__init__()
        self.cola = cola

    def emit(self, record: logging.LogRecord) -> None:
        """Publica el registro en la cola en vez de escribirlo en consola.

        Args:
            record: Registro emitido por el codigo de negocio.
        """
        try:
            self.cola.put(Mensaje(tipo=TipoMensaje.LOG, texto=self.format(record)))
        except Exception:  # pragma: no cover - un fallo del log no puede tumbar el proceso
            self.handleError(record)


class TrabajadorReconciliacion(threading.Thread):
    """Ejecuta el proceso completo en segundo plano.

    El hilo es `daemon` para que cerrar la ventana no deje el proceso colgado.
    Nunca toca un widget: todo lo que tiene que decir lo publica en la cola.
    """

    def __init__(
        self,
        cola: "queue.Queue[Mensaje]",
        servicio: Optional[ServicioReconciliacion] = None,
    ) -> None:
        """Crea el trabajador.

        Args:
            cola: Cola por la que se comunica con la interfaz.
            servicio: Servicio a ejecutar. Se inyecta para poder sustituirlo
                en pruebas.
        """
        super().__init__(daemon=True, name="reconciliacion")
        self.cola = cola
        self.servicio = servicio or ServicioReconciliacion()

    def run(self) -> None:
        """Corre la reconciliacion y publica avance, errores y resultado.

        Ninguna excepcion escapa de aqui: un fallo previsible se informa con su
        mensaje en el idioma del usuario y uno inesperado se informa como tal,
        pero en ambos casos la interfaz se entera y se libera. Un traceback en
        una consola que el usuario final nunca ve no le sirve a nadie.
        """
        logger = logging.getLogger(NOMBRE_LOGGER_RAIZ)
        handler = ManejadorCola(self.cola)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Python entrega el GIL cada 5 ms por defecto. Con este hilo al 100 %
        # de CPU eso deja al hilo de la ventana sin turnos suficientes para
        # repintar, y la interfaz se ve congelada. Bajarlo mientras dura el
        # proceso reparte el tiempo mucho mas fino; se restaura al terminar
        # para no alterar el resto del programa.
        intervalo_original = sys.getswitchinterval()
        sys.setswitchinterval(INTERVALO_CONMUTACION_SEGUNDOS)

        try:
            resultado = self.servicio.ejecutar(progreso=self._informar_progreso)
            self.cola.put(
                Mensaje(
                    tipo=TipoMensaje.FIN,
                    texto="Reconciliacion terminada.",
                    porcentaje=100,
                    resultado=resultado,
                )
            )
        except ErrorReconciliacion as error:
            self.cola.put(
                Mensaje(tipo=TipoMensaje.ERROR, texto=error.mensaje, detalle=error.detalle)
            )
        except Exception as error:  # noqa: BLE001 - la interfaz no puede caerse nunca
            self.cola.put(
                Mensaje(
                    tipo=TipoMensaje.ERROR,
                    texto="Ocurrio un error inesperado durante el proceso.",
                    detalle=f"{type(error).__name__}: {error}",
                )
            )
        finally:
            sys.setswitchinterval(intervalo_original)
            logger.removeHandler(handler)

    def _informar_progreso(self, texto: str, porcentaje: float) -> None:
        """Publica un avance en la cola y le cede el turno a la interfaz.

        Publicar en la cola no basta. Este hilo es intensivo en CPU, retiene el
        GIL y el hilo que dibuja la ventana no alcanza ni a leer la cola ni a
        repintar: medido, la ventana quedaba bloqueada 1,5 s y la barra saltaba
        de 0 a 100 al final, que es justo lo que hay que evitar.

        La pausa tiene que ser real. `sleep(0)` en Windows solo cede el turno a
        hilos que ya esten listos, y el de la interfaz suele estar esperando un
        evento, asi que no cambia nada; una pausa de 1 ms si lo despierta a
        tiempo. Como los avisos son por lotes, el costo total ronda las
        centesimas de segundo.

        Args:
            texto: Descripcion del paso actual.
            porcentaje: Avance acumulado, de 0 a 100.
        """
        self.cola.put(
            Mensaje(tipo=TipoMensaje.PROGRESO, texto=texto, porcentaje=porcentaje)
        )
        time.sleep(PAUSA_CESION_SEGUNDOS)
