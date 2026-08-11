"""Pruebas de las reglas de clasificacion."""

from __future__ import annotations

from datetime import datetime

from reconciliacion.dominio.enums import Clasificacion
from reconciliacion.procesamiento.reglas import (
    REGLAS_POR_DEFECTO,
    ReglaEstado,
    ReglaFechas,
    ReglaMonto,
    ReglaPresencia,
    ReglaReconciliado,
    formatear_monto,
)


def clasificar(transaccion):
    """Aplica todas las reglas en orden, como lo hace el reconciliador."""
    for regla in REGLAS_POR_DEFECTO:
        regla.aplicar(transaccion)
    return transaccion.clasificaciones


class TestReglaPresencia:
    """Cubre las siete combinaciones, no solo las tres del enunciado."""

    def test_falta_en_json(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_json=False)
        ReglaPresencia().aplicar(transaccion)
        assert transaccion.clasificaciones == [Clasificacion.NO_ENCONTRADO_EN_JSON]

    def test_falta_en_sqlite(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_sqlite=False)
        ReglaPresencia().aplicar(transaccion)
        assert transaccion.clasificaciones == [Clasificacion.NO_CONTABILIZADO]

    def test_solo_en_json_es_no_autorizado(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_csv=False, en_sqlite=False)
        ReglaPresencia().aplicar(transaccion)
        assert transaccion.clasificaciones == [Clasificacion.NO_AUTORIZADO]

    def test_solo_en_csv_acumula_las_dos_etiquetas(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_sqlite=False, en_json=False)
        ReglaPresencia().aplicar(transaccion)
        assert set(transaccion.clasificaciones) == {
            Clasificacion.NO_CONTABILIZADO,
            Clasificacion.NO_ENCONTRADO_EN_JSON,
        }

    def test_presente_en_las_tres_no_genera_etiqueta(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion()
        ReglaPresencia().aplicar(transaccion)
        assert transaccion.clasificaciones == []


class TestReglaMonto:
    """Los montos deben coincidir exactamente."""

    def test_detecta_la_diferencia(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(csv_monto=225_000.0, sql_monto=230_000.0, json_monto=230_000.0)
        ReglaMonto().aplicar(transaccion)
        assert transaccion.clasificaciones == [Clasificacion.DISCREPANCIA_MONTO]
        assert transaccion.diferencia_monto == 5_000.0

    def test_la_observacion_explica_el_hallazgo(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(csv_monto=225_000.0, sql_monto=230_000.0, json_monto=230_000.0)
        ReglaMonto().aplicar(transaccion)
        observacion = transaccion.observaciones[0]
        assert "225.000" in observacion and "230.000" in observacion and "5.000" in observacion

    def test_montos_iguales_no_generan_etiqueta(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion()
        ReglaMonto().aplicar(transaccion)
        assert transaccion.clasificaciones == []

    def test_una_sola_fuente_no_puede_discrepar(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_sqlite=False, en_json=False)
        ReglaMonto().aplicar(transaccion)
        assert transaccion.clasificaciones == []


class TestReglaEstado:
    """Cada fuente tiene su vocabulario; solo SQLite define la discrepancia."""

    def test_vocabularios_distintos_no_son_discrepancia(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion()
        assert transaccion.estado_csv == "AUTORIZADO"
        assert transaccion.estado_sqlite == "CONTABILIZADO"
        assert transaccion.estado_json == "COMPLETADO"
        ReglaEstado().aplicar(transaccion)
        assert transaccion.clasificaciones == []

    def test_pendiente_en_sqlite_es_discrepancia(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(sql_estado="PENDIENTE")
        ReglaEstado().aplicar(transaccion)
        assert transaccion.clasificaciones == [Clasificacion.DISCREPANCIA_ESTADO]

    def test_rechazado_en_sqlite_es_discrepancia(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(sql_estado="RECHAZADO")
        ReglaEstado().aplicar(transaccion)
        assert transaccion.clasificaciones == [Clasificacion.DISCREPANCIA_ESTADO]
        assert "RECHAZADO" in transaccion.observaciones[0]

    def test_sin_sqlite_no_hay_estado_que_evaluar(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_sqlite=False)
        ReglaEstado().aplicar(transaccion)
        assert transaccion.clasificaciones == []


class TestReglaFechas:
    """La tolerancia es de +-2 horas y queda como observacion."""

    def test_dentro_de_la_tolerancia_no_dice_nada(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(sql_fecha=datetime(2026, 7, 15, 16, 0))
        ReglaFechas().aplicar(transaccion)
        assert transaccion.observaciones == []

    def test_fuera_de_la_tolerancia_deja_observacion_sin_etiqueta(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(sql_fecha=datetime(2026, 7, 15, 20, 0))
        ReglaFechas().aplicar(transaccion)
        assert transaccion.clasificaciones == []
        assert "desfase" in transaccion.observaciones[0]


class TestReglaReconciliado:
    """Es la unica etiqueta excluyente."""

    def test_todo_cuadra(self, fabricar_transaccion) -> None:
        assert clasificar(fabricar_transaccion()) == [Clasificacion.RECONCILIADO]

    def test_no_aplica_si_ya_hay_un_hallazgo(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(sql_estado="RECHAZADO")
        assert clasificar(transaccion) == [Clasificacion.DISCREPANCIA_ESTADO]

    def test_no_aplica_si_falta_una_fuente(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_json=False)
        assert Clasificacion.RECONCILIADO not in clasificar(transaccion)

    def test_exige_estado_contabilizado(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(sql_estado="PENDIENTE")
        ReglaReconciliado().aplicar(transaccion)
        assert transaccion.clasificaciones == []


class TestClasificacionMultiEtiqueta:
    """Una transaccion puede acumular varios hallazgos a la vez."""

    def test_faltante_y_discrepancia_de_monto(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_json=False, csv_monto=100_000.0, sql_monto=120_000.0)
        etiquetas = clasificar(transaccion)
        assert set(etiquetas) == {
            Clasificacion.NO_ENCONTRADO_EN_JSON,
            Clasificacion.DISCREPANCIA_MONTO,
        }

    def test_toda_transaccion_queda_clasificada(self, fabricar_transaccion) -> None:
        for kwargs in (
            {},
            {"en_csv": False, "en_sqlite": False},
            {"en_sqlite": False},
            {"en_json": False},
            {"en_sqlite": False, "en_json": False},
            {"en_csv": False},
            {"en_csv": False, "en_json": False},
        ):
            assert clasificar(fabricar_transaccion(**kwargs)), f"sin clasificar: {kwargs}"


def test_formatear_monto() -> None:
    assert formatear_monto(1_250_000.0) == "1.250.000"
    assert formatear_monto(0.0) == "0"
    assert formatear_monto(None) == "sin dato"
