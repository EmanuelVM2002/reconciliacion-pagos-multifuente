"""Pruebas de la transaccion reconciliada y sus magnitudes derivadas."""

from __future__ import annotations

from datetime import datetime

from reconciliacion.dominio.transaccion import TransaccionReconciliada


class TestMontoReferencia:
    """Es el valor que representa a la transaccion en fraude y en patron."""

    def test_manda_la_mayoria(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(csv_monto=100_000.0, sql_monto=120_000.0, json_monto=120_000.0)
        assert transaccion.monto_referencia == 120_000.0

    def test_con_empate_gana_el_mayor(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_json=False, csv_monto=100_000.0, sql_monto=120_000.0)
        assert transaccion.monto_referencia == 120_000.0

    def test_con_una_sola_fuente_es_ese_monto(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_csv=False, en_sqlite=False, json_monto=77_000.0)
        assert transaccion.monto_referencia == 77_000.0

    def test_sin_montos_es_none(self) -> None:
        assert TransaccionReconciliada(id_transaccion="TRX0001").monto_referencia is None


class TestDiferenciaMonto:
    """Es el maximo menos el minimo entre las fuentes presentes."""

    def test_cero_si_todas_coinciden(self, fabricar_transaccion) -> None:
        assert fabricar_transaccion().diferencia_monto == 0.0

    def test_maximo_menos_minimo(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(csv_monto=100_000.0, sql_monto=120_000.0, json_monto=110_000.0)
        assert transaccion.diferencia_monto == 20_000.0

    def test_una_sola_fuente_no_puede_diferir(self, fabricar_transaccion) -> None:
        assert fabricar_transaccion(en_sqlite=False, en_json=False).diferencia_monto == 0.0


class TestFechaReferencia:
    """Prioridad CSV -> SQLite -> JSON (ver README)."""

    def test_prefiere_la_del_csv(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(
            csv_fecha=datetime(2026, 7, 15, 9, 0), sql_fecha=datetime(2026, 7, 15, 10, 0)
        )
        assert transaccion.fecha_referencia == datetime(2026, 7, 15, 9, 0)

    def test_cae_a_sqlite_si_no_hay_csv(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_csv=False, sql_fecha=datetime(2026, 7, 15, 10, 0))
        assert transaccion.fecha_referencia == datetime(2026, 7, 15, 10, 0)

    def test_cae_a_json_si_es_lo_unico(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(
            en_csv=False, en_sqlite=False, json_fecha=datetime(2026, 7, 15, 11, 0)
        )
        assert transaccion.fecha_referencia == datetime(2026, 7, 15, 11, 0)


class TestPresenciaYBanco:
    """Presencia por fuente y entidad bancaria."""

    def test_cuenta_las_fuentes_presentes(self, fabricar_transaccion) -> None:
        assert fabricar_transaccion().fuentes_presentes == 3
        assert fabricar_transaccion(en_json=False).fuentes_presentes == 2
        assert fabricar_transaccion(en_csv=False, en_sqlite=False).fuentes_presentes == 1

    def test_banderas_de_presencia(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_sqlite=False)
        assert transaccion.presente_csv is True
        assert transaccion.presente_sqlite is False
        assert transaccion.presente_json is True

    def test_toma_el_banco_de_la_primera_fuente_disponible(self, fabricar_transaccion) -> None:
        transaccion = fabricar_transaccion(en_csv=False, sql_banco="BANCO_C")
        assert transaccion.banco == "BANCO_C"

    def test_sin_fuentes_no_hay_banco(self) -> None:
        assert TransaccionReconciliada(id_transaccion="TRX0001").banco is None
