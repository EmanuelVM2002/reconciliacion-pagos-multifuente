"""Orquestacion del proceso completo de reconciliacion.

Este es el unico punto que conoce el proceso de principio a fin: verificar las
fuentes, cargarlas, limpiarlas, reconciliarlas, detectar fraude y exportar el
reporte.

Existe para que la terminal y la interfaz grafica ejecuten **exactamente el
mismo codigo**. La GUI no reimplementa nada: llama a este servicio pasandole
una funcion de progreso, y ese es el unico acoplamiento entre ambos mundos.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from reconciliacion.config import rutas
from reconciliacion.dominio.transaccion import TransaccionReconciliada
from reconciliacion.errores import FuenteNoDisponibleError
from reconciliacion.exportadores.excel import ExportadorExcel
from reconciliacion.limpieza.autorizaciones import ResultadoLimpieza, limpiar_autorizaciones
from reconciliacion.loaders import (
    CargadorAutorizaciones,
    CargadorContabilizaciones,
    CargadorMovimientos,
)
from reconciliacion.log import obtener_logger
from reconciliacion.procesamiento.fraude import DetectorFraude, ResumenFraude
from reconciliacion.procesamiento.reconciliador import Reconciliador, ResumenReconciliacion
from reconciliacion.progreso import ProgresoParcial

_log = obtener_logger(__name__)

#: Firma de la funcion de progreso: (mensaje, porcentaje 0-100).
FuncionProgreso = Callable[[str, float], None]


@dataclass
class ResultadoProceso:
    """Todo lo que produce una ejecucion completa.

    Attributes:
        transacciones: Universo reconciliado y evaluado.
        resumen: Indicadores de reconciliacion.
        resumen_fraude: Indicadores de fraude.
        limpieza: Detalle del parseo del CSV.
        registros_por_fuente: Cuantos registros aporto cada fuente.
        advertencias: Problemas de integridad detectados al cargar.
        ruta_reporte: Ubicacion del Excel generado.
        duracion_segundos: Tiempo total del proceso.
    """

    transacciones: List[TransaccionReconciliada] = field(default_factory=list)
    resumen: ResumenReconciliacion = field(default_factory=ResumenReconciliacion)
    resumen_fraude: ResumenFraude = field(default_factory=ResumenFraude)
    limpieza: Optional[ResultadoLimpieza] = None
    registros_por_fuente: Dict[str, int] = field(default_factory=dict)
    advertencias: List[str] = field(default_factory=list)
    ruta_reporte: Optional[Path] = None
    duracion_segundos: float = 0.0


class ServicioReconciliacion:
    """Ejecuta el proceso completo y reporta el avance.

    Attributes:
        reconciliador: Motor de cruce y clasificacion.
        detector: Detector de patrones de fraude.
        exportador: Generador del reporte Excel.
    """

    def __init__(
        self,
        reconciliador: Optional[Reconciliador] = None,
        detector: Optional[DetectorFraude] = None,
        exportador: Optional[ExportadorExcel] = None,
    ) -> None:
        """Crea el servicio.

        Args:
            reconciliador: Motor de reconciliacion. Se inyecta para poder
                sustituirlo en los tests.
            detector: Detector de fraude.
            exportador: Exportador del reporte.
        """
        self.reconciliador = reconciliador or Reconciliador()
        self.detector = detector or DetectorFraude()
        self.exportador = exportador or ExportadorExcel()

    def ejecutar(
        self,
        progreso: Optional[FuncionProgreso] = None,
        exportar: bool = True,
    ) -> ResultadoProceso:
        """Corre la reconciliacion de principio a fin.

        Args:
            progreso: Funcion a la que se le informa cada avance. Recibe el
                mensaje y el porcentaje acumulado. Si se omite, el avance solo
                queda en el log.
            exportar: Si es `False` se hace todo el calculo pero no se escribe
                el Excel (util en pruebas).

        Returns:
            El resultado completo del proceso.

        Raises:
            FuenteNoDisponibleError: Si falta algun archivo de entrada.
            FuenteCorruptaError: Si alguna fuente no se puede interpretar.
            ErrorExportacion: Si no se puede escribir el reporte.
        """
        inicio = time.perf_counter()
        resultado = ResultadoProceso()
        avisar = progreso or (lambda mensaje, porcentaje: None)

        avisar("Verificando archivos de entrada...", 2)
        self._verificar_fuentes()

        avisar("Cargando autorizaciones (CSV)...", 10)
        carga_csv = CargadorAutorizaciones().cargar()

        avisar("Cargando contabilizaciones (SQLite)...", 22)
        carga_sqlite = CargadorContabilizaciones().cargar()

        avisar("Cargando movimientos bancarios (JSON)...", 34)
        carga_json = CargadorMovimientos().cargar()

        for carga in (carga_csv, carga_sqlite, carga_json):
            resultado.registros_por_fuente[carga.fuente] = carga.total
            resultado.advertencias.extend(f"{carga.fuente}: {a}" for a in carga.advertencias)

        avisar("Limpiando los campos malformados del CSV...", 40)
        resultado.limpieza = limpiar_autorizaciones(
            carga_csv.registros,
            progreso=self._parcial(avisar, "Limpiando el CSV", 40, 58),
        )
        resultado.advertencias.extend(resultado.limpieza.incidencias)

        avisar("Cruzando las tres fuentes...", 58)
        resultado.transacciones = self.reconciliador.reconciliar(
            resultado.limpieza.autorizaciones,
            carga_sqlite.registros,
            carga_json.registros,
            progreso=self._parcial(avisar, "Clasificando transacciones", 58, 76),
        )

        avisar("Buscando patrones de fraude...", 76)
        resultado.resumen_fraude = self.detector.detectar(resultado.transacciones)
        resultado.resumen = self.reconciliador.resumir(resultado.transacciones)

        if exportar:
            avisar("Generando el reporte de Excel...", 84)
            resultado.ruta_reporte = self.exportador.exportar(
                resultado.transacciones,
                progreso=self._parcial(avisar, "Escribiendo el reporte", 84, 99),
            )

        resultado.duracion_segundos = time.perf_counter() - inicio
        avisar("Proceso terminado.", 100)
        _log.info(
            "Proceso completo en %.2f s: %d transacciones, %d fraudes",
            resultado.duracion_segundos,
            resultado.resumen.total,
            resultado.resumen_fraude.total_fraudes,
        )
        return resultado

    @staticmethod
    def _parcial(
        avisar: FuncionProgreso, mensaje: str, desde: float, hasta: float
    ) -> ProgresoParcial:
        """Traduce el avance de una etapa al porcentaje global del proceso.

        Cada etapa larga cuenta sus propios elementos (filas, transacciones) sin
        saber que porcion del total representa. Esta funcion hace esa
        conversion, de modo que la barra avanza de forma continua y no a
        saltos entre etapa y etapa.

        Args:
            avisar: Funcion de progreso global.
            mensaje: Texto a mostrar durante la etapa.
            desde: Porcentaje global en que empieza la etapa.
            hasta: Porcentaje global en que termina.

        Returns:
            La funcion de avance parcial que espera la etapa.
        """

        def reportar(procesados: int, total: int) -> None:
            fraccion = procesados / total if total else 1.0
            avisar(
                f"{mensaje}... ({procesados}/{total})",
                desde + (hasta - desde) * fraccion,
            )

        return reportar

    @staticmethod
    def _verificar_fuentes() -> None:
        """Comprueba que las tres fuentes existan antes de empezar.

        Se valida todo de una vez para poder decirle al usuario **todo** lo que
        le falta en un solo mensaje, en lugar de hacerlo fallar tres veces
        seguidas.

        Raises:
            FuenteNoDisponibleError: Si falta al menos una fuente.
        """
        faltantes = rutas.fuentes_faltantes()
        if faltantes:
            raise FuenteNoDisponibleError(
                "No se encontraron estos archivos de datos: " + ", ".join(faltantes) + ".",
                detalle=f"Se buscaron en: {rutas.DIRECTORIO_DATOS}",
            )
