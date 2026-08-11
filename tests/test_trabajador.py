"""Pruebas del hilo de trabajo de la interfaz.

Se prueban sin abrir ninguna ventana: el trabajador solo habla con una cola,
asi que basta con leerla. Eso permite verificar la cancelacion y el manejo de
errores en un entorno sin pantalla, como el de integracion continua.
"""

from __future__ import annotations

import queue
import time
from typing import List, Optional

import pytest

from reconciliacion.errores import ErrorExportacion, ProcesoCancelado
from reconciliacion.gui.mensajes import Mensaje, TipoMensaje
from reconciliacion.gui.trabajador import TrabajadorReconciliacion


class ServicioLento:
    """Servicio de mentira que avisa muchas veces y nunca termina rapido."""

    def __init__(self, pasos: int = 200) -> None:
        self.pasos = pasos
        self.pasos_ejecutados = 0

    def ejecutar(self, progreso=None, exportar: bool = True):
        for numero in range(self.pasos):
            self.pasos_ejecutados = numero + 1
            if progreso is not None:
                progreso(f"Paso {numero}", numero / self.pasos * 100)
            time.sleep(0.002)
        return "terminado"


class ServicioQueFalla:
    """Servicio que lanza un error previsible del dominio."""

    def ejecutar(self, progreso=None, exportar: bool = True):
        raise ErrorExportacion("El archivo esta abierto.", detalle="PermissionError")


class ServicioQueExplota:
    """Servicio que lanza un error que nadie previo."""

    def ejecutar(self, progreso=None, exportar: bool = True):
        raise ZeroDivisionError("division by zero")


def vaciar(cola: "queue.Queue[Mensaje]") -> List[Mensaje]:
    """Devuelve todos los mensajes pendientes en la cola."""
    mensajes: List[Mensaje] = []
    while True:
        try:
            mensajes.append(cola.get_nowait())
        except queue.Empty:
            return mensajes


def esperar(trabajador: TrabajadorReconciliacion, segundos: float = 10) -> None:
    """Espera a que el hilo termine, con un tope para no colgar la prueba."""
    trabajador.join(timeout=segundos)
    assert not trabajador.is_alive(), "el hilo no termino a tiempo"


class TestCancelacion:
    def test_cancelar_detiene_el_proceso_antes_de_terminar(self) -> None:
        cola: "queue.Queue[Mensaje]" = queue.Queue()
        servicio = ServicioLento(pasos=500)
        trabajador = TrabajadorReconciliacion(cola, servicio=servicio)

        trabajador.start()
        time.sleep(0.15)
        trabajador.cancelar()
        esperar(trabajador)

        assert servicio.pasos_ejecutados < servicio.pasos

    def test_avisa_de_la_cancelacion_y_no_como_error(self) -> None:
        cola: "queue.Queue[Mensaje]" = queue.Queue()
        trabajador = TrabajadorReconciliacion(cola, servicio=ServicioLento(pasos=500))

        trabajador.start()
        time.sleep(0.1)
        trabajador.cancelar()
        esperar(trabajador)

        tipos = [m.tipo for m in vaciar(cola)]
        assert TipoMensaje.CANCELADO in tipos
        assert TipoMensaje.ERROR not in tipos
        assert TipoMensaje.FIN not in tipos

    def test_cancelar_antes_de_empezar_no_ejecuta_nada(self) -> None:
        cola: "queue.Queue[Mensaje]" = queue.Queue()
        servicio = ServicioLento(pasos=50)
        trabajador = TrabajadorReconciliacion(cola, servicio=servicio)

        trabajador.cancelar()
        trabajador.start()
        esperar(trabajador)

        assert servicio.pasos_ejecutados <= 1


class TestManejoDeErrores:
    def test_un_error_previsible_llega_con_su_mensaje(self) -> None:
        cola: "queue.Queue[Mensaje]" = queue.Queue()
        trabajador = TrabajadorReconciliacion(cola, servicio=ServicioQueFalla())

        trabajador.start()
        esperar(trabajador)

        errores = [m for m in vaciar(cola) if m.tipo is TipoMensaje.ERROR]
        assert len(errores) == 1
        assert errores[0].texto == "El archivo esta abierto."
        assert errores[0].detalle == "PermissionError"

    def test_un_error_inesperado_no_tumba_el_hilo(self) -> None:
        cola: "queue.Queue[Mensaje]" = queue.Queue()
        trabajador = TrabajadorReconciliacion(cola, servicio=ServicioQueExplota())

        trabajador.start()
        esperar(trabajador)

        errores = [m for m in vaciar(cola) if m.tipo is TipoMensaje.ERROR]
        assert len(errores) == 1
        assert "inesperado" in errores[0].texto
        assert "ZeroDivisionError" in errores[0].detalle


class TestProgreso:
    def test_publica_el_avance_en_la_cola(self) -> None:
        cola: "queue.Queue[Mensaje]" = queue.Queue()
        trabajador = TrabajadorReconciliacion(cola, servicio=ServicioLento(pasos=10))

        trabajador.start()
        esperar(trabajador)

        mensajes = vaciar(cola)
        avances = [m for m in mensajes if m.tipo is TipoMensaje.PROGRESO]
        assert len(avances) == 10
        assert [m.porcentaje for m in avances] == sorted(m.porcentaje for m in avances)
        assert mensajes[-1].tipo is TipoMensaje.FIN

    def test_restaura_el_intervalo_de_conmutacion_al_terminar(self) -> None:
        import sys

        original = sys.getswitchinterval()
        cola: "queue.Queue[Mensaje]" = queue.Queue()
        trabajador = TrabajadorReconciliacion(cola, servicio=ServicioLento(pasos=5))

        trabajador.start()
        esperar(trabajador)

        assert sys.getswitchinterval() == original
