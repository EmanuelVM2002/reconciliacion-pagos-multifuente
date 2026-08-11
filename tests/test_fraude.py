"""Pruebas de los cuatro patrones de fraude y del nivel de riesgo."""

from __future__ import annotations

from datetime import datetime

from reconciliacion.dominio.enums import NivelRiesgo, TipoFraude
from reconciliacion.procesamiento.fraude import (
    DetectorFraude,
    ReglaHoraInusual,
    ReglaMontoAnomalo,
    ReglaPatronSospechoso,
    ReglaSinAutorizacion,
)


class TestReglaMontoAnomalo:
    """Anomalo es lo que supera media + 3 sigma del conjunto."""

    def test_marca_solo_el_valor_extremo(self, fabricar_transaccion) -> None:
        normales = [
            fabricar_transaccion(
                id_transaccion=f"TRX{i:04d}", csv_monto=100_000.0, sql_monto=100_000.0, json_monto=100_000.0
            )
            for i in range(30)
        ]
        extrema = fabricar_transaccion(
            id_transaccion="TRX9999", csv_monto=9_000_000.0, sql_monto=9_000_000.0, json_monto=9_000_000.0
        )
        ReglaMontoAnomalo().detectar([*normales, extrema])

        assert extrema.tipos_fraude == [TipoFraude.MONTO]
        assert all(not t.tipos_fraude for t in normales)

    def test_expone_el_umbral_calculado(self, fabricar_transaccion) -> None:
        regla = ReglaMontoAnomalo()
        regla.detectar([fabricar_transaccion(id_transaccion=f"T{i}") for i in range(5)])
        assert regla.umbral > 0

    def test_no_revienta_con_una_sola_transaccion(self, fabricar_transaccion) -> None:
        ReglaMontoAnomalo().detectar([fabricar_transaccion()])  # no debe lanzar


class TestReglaHoraInusual:
    """La franja sospechosa es 00:00 a 05:59 inclusive."""

    def test_marca_la_madrugada(self, fabricar_transaccion) -> None:
        for hora in (0, 3, 5):
            transaccion = fabricar_transaccion(csv_fecha=datetime(2026, 7, 15, hora, 30))
            ReglaHoraInusual().detectar([transaccion])
            assert transaccion.tipos_fraude == [TipoFraude.HORA], f"hora {hora}"

    def test_las_05_59_todavia_cuentan(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(csv_fecha=datetime(2026, 7, 15, 5, 59))
        ReglaHoraInusual().detectar([transaccion])
        assert transaccion.tipos_fraude == [TipoFraude.HORA]

    def test_las_06_00_ya_no(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(csv_fecha=datetime(2026, 7, 15, 6, 0))
        ReglaHoraInusual().detectar([transaccion])
        assert transaccion.tipos_fraude == []


class TestReglaPatronSospechoso:
    """Mismo banco, mismo monto y menos de 60 minutos de diferencia."""

    def test_marca_las_dos_transacciones_involucradas(self, fabricar_transaccion) -> None:
        una = fabricar_transaccion(id_transaccion="TRX0001", csv_fecha=datetime(2026, 7, 15, 10, 0))
        otra = fabricar_transaccion(id_transaccion="TRX0002", csv_fecha=datetime(2026, 7, 15, 10, 45))
        ReglaPatronSospechoso().detectar([una, otra])

        assert una.tipos_fraude == [TipoFraude.PATRON]
        assert otra.tipos_fraude == [TipoFraude.PATRON]

    def test_la_observacion_nombra_a_la_otra(self, fabricar_transaccion) -> None:
        una = fabricar_transaccion(id_transaccion="TRX0001", csv_fecha=datetime(2026, 7, 15, 10, 0))
        otra = fabricar_transaccion(id_transaccion="TRX0002", csv_fecha=datetime(2026, 7, 15, 10, 45))
        ReglaPatronSospechoso().detectar([una, otra])
        assert "TRX0002" in una.observaciones[0]

    def test_justo_en_60_minutos_todavia_cuenta(self, fabricar_transaccion) -> None:
        una = fabricar_transaccion(id_transaccion="A", csv_fecha=datetime(2026, 7, 15, 10, 0))
        otra = fabricar_transaccion(id_transaccion="B", csv_fecha=datetime(2026, 7, 15, 11, 0))
        ReglaPatronSospechoso().detectar([una, otra])
        assert una.tipos_fraude == [TipoFraude.PATRON]

    def test_mas_de_60_minutos_no_cuenta(self, fabricar_transaccion) -> None:
        una = fabricar_transaccion(id_transaccion="A", csv_fecha=datetime(2026, 7, 15, 10, 0))
        otra = fabricar_transaccion(id_transaccion="B", csv_fecha=datetime(2026, 7, 15, 11, 1))
        ReglaPatronSospechoso().detectar([una, otra])
        assert una.tipos_fraude == []

    def test_distinto_banco_no_cuenta(self, fabricar_transaccion) -> None:
        una = fabricar_transaccion(id_transaccion="A", csv_banco="BANCO_A", sql_banco="BANCO_A", json_banco="BANCO_A")
        otra = fabricar_transaccion(id_transaccion="B", csv_banco="BANCO_C", sql_banco="BANCO_C", json_banco="BANCO_C")
        ReglaPatronSospechoso().detectar([una, otra])
        assert una.tipos_fraude == []

    def test_distinto_monto_no_cuenta(self, fabricar_transaccion) -> None:
        una = fabricar_transaccion(id_transaccion="A")
        otra = fabricar_transaccion(
            id_transaccion="B", csv_monto=999_000.0, sql_monto=999_000.0, json_monto=999_000.0
        )
        ReglaPatronSospechoso().detectar([una, otra])
        assert una.tipos_fraude == []

    def test_marca_a_las_tres_de_un_grupo(self, fabricar_transaccion) -> None:
        grupo = [
            fabricar_transaccion(id_transaccion=f"T{i}", csv_fecha=datetime(2026, 7, 15, 10, i * 20))
            for i in range(3)
        ]
        ReglaPatronSospechoso().detectar(grupo)
        assert all(t.tipos_fraude == [TipoFraude.PATRON] for t in grupo)


class TestReglaSinAutorizacion:
    """El banco no puede mover plata que nadie autorizo."""

    def test_marca_lo_que_solo_esta_en_el_banco(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_csv=False, en_sqlite=False)
        ReglaSinAutorizacion().detectar([transaccion])
        assert transaccion.tipos_fraude == [TipoFraude.NO_AUTORIZADO]

    def test_no_marca_lo_autorizado(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion()
        ReglaSinAutorizacion().detectar([transaccion])
        assert transaccion.tipos_fraude == []


class TestNivelRiesgo:
    """Con varios fraudes manda el mas grave."""

    def test_sin_fraude_no_hay_nivel(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion()
        assert transaccion.es_fraude is False
        assert transaccion.nivel_riesgo is None

    def test_no_autorizado_es_critico(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion()
        transaccion.tipos_fraude = [TipoFraude.HORA, TipoFraude.MONTO, TipoFraude.NO_AUTORIZADO]
        assert transaccion.nivel_riesgo is NivelRiesgo.CRITICO

    def test_monto_es_alto(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion()
        transaccion.tipos_fraude = [TipoFraude.HORA, TipoFraude.MONTO]
        assert transaccion.nivel_riesgo is NivelRiesgo.ALTO

    def test_hora_y_patron_son_medio(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion()
        transaccion.tipos_fraude = [TipoFraude.HORA, TipoFraude.PATRON]
        assert transaccion.nivel_riesgo is NivelRiesgo.MEDIO


class TestDetectorFraude:
    """El detector es transversal a la clasificacion."""

    def test_una_transaccion_reconciliada_puede_ser_fraude(self, fabricar_transaccion) -> None:
        from reconciliacion.procesamiento.reglas import REGLAS_POR_DEFECTO

        transaccion = fabricar_transaccion(csv_fecha=datetime(2026, 7, 15, 3, 14))
        for regla in REGLAS_POR_DEFECTO:
            regla.aplicar(transaccion)
        DetectorFraude().detectar([transaccion])

        assert transaccion.esta_reconciliada is True
        assert transaccion.es_fraude is True

    def test_el_resumen_cuenta_por_tipo_y_por_nivel(self, fabricar_transaccion) -> None:
        transacciones = [
            fabricar_transaccion(id_transaccion="A", csv_fecha=datetime(2026, 7, 15, 2, 0)),
            fabricar_transaccion(id_transaccion="B", en_csv=False, en_sqlite=False),
        ]
        resumen = DetectorFraude().detectar(transacciones)

        assert resumen.total_fraudes == 2
        assert resumen.por_tipo[str(TipoFraude.HORA)] >= 1
        assert resumen.por_nivel[str(NivelRiesgo.CRITICO)] == 1
