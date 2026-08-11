"""Prueba de extremo a extremo sobre los datos reales del enunciado.

Las demas pruebas aislan cada pieza; esta corre la cadena completa y fija los
numeros que debe producir. Si alguien cambia un parser, una regla o el umbral
de fraude y los totales se mueven, esta prueba lo detecta de inmediato.
"""

from __future__ import annotations

import pytest

from reconciliacion.config import rutas
from reconciliacion.dominio.enums import Clasificacion, TipoFraude
from reconciliacion.servicio import ServicioReconciliacion

pytestmark = pytest.mark.skipif(
    bool(rutas.fuentes_faltantes()),
    reason="requiere los tres archivos de datos en la carpeta datos/",
)


@pytest.fixture(scope="module")
def resultado():
    """Corre el proceso una sola vez para todas las pruebas del modulo."""
    return ServicioReconciliacion().ejecutar(exportar=False)


class TestCarga:
    def test_las_tres_fuentes_aportan_lo_esperado(self, resultado) -> None:
        assert resultado.registros_por_fuente == {
            "Autorizaciones (CSV)": 500,
            "Contabilizaciones (SQLite)": 480,
            "Movimientos bancarios (JSON)": 465,
        }


class TestLimpieza:
    def test_no_se_pierde_ninguna_fila_del_csv(self, resultado) -> None:
        limpieza = resultado.limpieza
        assert limpieza.filas_procesadas == 500
        assert len(limpieza.autorizaciones) == 500

    def test_se_extrajo_todo_de_las_500_filas(self, resultado) -> None:
        limpieza = resultado.limpieza
        assert limpieza.sin_monto == 0
        assert limpieza.sin_marca == 0
        assert limpieza.sin_retenciones == 0
        assert limpieza.extraccion_completa is True

    def test_la_unica_incidencia_es_la_clave_monto_duplicada(self, resultado) -> None:
        assert resultado.limpieza.con_monto_duplicado == 1
        assert any("TRX0138" in i for i in resultado.limpieza.incidencias)


class TestReconciliacion:
    def test_el_universo_es_la_union_de_las_tres_fuentes(self, resultado) -> None:
        assert resultado.resumen.total == 505

    def test_ninguna_transaccion_queda_sin_clasificar(self, resultado) -> None:
        sin_clasificar = [t.id_transaccion for t in resultado.transacciones if not t.clasificaciones]
        assert sin_clasificar == []

    def test_conteo_por_clasificacion(self, resultado) -> None:
        assert resultado.resumen.por_clasificacion == {
            str(Clasificacion.RECONCILIADO): 290,
            str(Clasificacion.DISCREPANCIA_MONTO): 95,
            str(Clasificacion.DISCREPANCIA_ESTADO): 55,
            str(Clasificacion.NO_ENCONTRADO_EN_JSON): 40,
            str(Clasificacion.NO_CONTABILIZADO): 20,
            str(Clasificacion.NO_AUTORIZADO): 5,
        }

    def test_las_etiquetas_suman_el_universo(self, resultado) -> None:
        assert sum(resultado.resumen.por_clasificacion.values()) == 505

    def test_reconciliado_nunca_va_acompanado(self, resultado) -> None:
        acompanadas = [
            t.id_transaccion
            for t in resultado.transacciones
            if Clasificacion.RECONCILIADO in t.clasificaciones and len(t.clasificaciones) > 1
        ]
        assert acompanadas == []

    def test_porcentaje_de_reconciliacion(self, resultado) -> None:
        assert round(resultado.resumen.porcentaje_reconciliacion, 1) == 57.4


class TestFraude:
    def test_conteo_por_patron(self, resultado) -> None:
        assert resultado.resumen_fraude.por_tipo == {
            str(TipoFraude.HORA): 134,
            str(TipoFraude.PATRON): 12,
            str(TipoFraude.MONTO): 11,
            str(TipoFraude.NO_AUTORIZADO): 5,
        }

    def test_total_de_transacciones_con_fraude(self, resultado) -> None:
        assert resultado.resumen_fraude.total_fraudes == 149

    def test_el_fraude_es_transversal_a_la_clasificacion(self, resultado) -> None:
        """Hay transacciones reconciliadas que ademas son fraude."""
        reconciliadas_con_fraude = [
            t for t in resultado.transacciones if t.esta_reconciliada and t.es_fraude
        ]
        assert len(reconciliadas_con_fraude) == 90

    def test_toda_transaccion_no_autorizada_es_critica(self, resultado) -> None:
        no_autorizadas = [
            t for t in resultado.transacciones if not t.presente_csv and t.presente_json
        ]
        assert len(no_autorizadas) == 5
        assert all(str(t.nivel_riesgo) == "CRÍTICO" for t in no_autorizadas)

    def test_el_nivel_de_riesgo_es_coherente(self, resultado) -> None:
        incoherentes = [
            t.id_transaccion
            for t in resultado.transacciones
            if t.es_fraude != (t.nivel_riesgo is not None)
        ]
        assert incoherentes == []


class TestExportacion:
    def test_genera_el_archivo_en_la_ruta_configurada(self, tmp_path) -> None:
        servicio = ServicioReconciliacion()
        resultado = servicio.ejecutar(exportar=False)
        destino = servicio.exportador.exportar(
            resultado.transacciones, ruta=tmp_path / "reporte.xlsx"
        )
        assert destino.exists()
        assert destino.stat().st_size > 0


class TestProgreso:
    def test_informa_el_avance_de_forma_creciente(self) -> None:
        avances = []
        ServicioReconciliacion().ejecutar(
            progreso=lambda texto, pct: avances.append(pct), exportar=False
        )
        assert len(avances) > 10, "el avance debe reportarse durante el proceso"
        assert avances == sorted(avances), "el porcentaje nunca debe retroceder"
        assert avances[-1] == 100
