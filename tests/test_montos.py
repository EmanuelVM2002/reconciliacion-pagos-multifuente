"""Pruebas de la extraccion del monto desde el campo malformado del CSV.

Los casos vienen del archivo real: son las variantes de corrupcion y de
formato que efectivamente aparecen en `autorizaciones.csv`.
"""

from __future__ import annotations

import pytest

from reconciliacion.limpieza.montos import (
    extraer_monto,
    extraer_montos,
    normalizar_valor_monetario,
)


class TestNormalizarValorMonetario:
    """El mismo importe viene escrito de tres maneras distintas."""

    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            ("1250000", 1_250_000.0),
            ('"188.000 COP"', 188_000.0),
            ('"$175.000,00"', 175_000.0),
            ("410.000", 410_000.0),
            ('"$95.000,00"', 95_000.0),
            ("1720000", 1_720_000.0),
        ],
    )
    def test_reconoce_los_formatos_del_archivo(self, texto: str, esperado: float) -> None:
        assert normalizar_valor_monetario(texto) == esperado

    def test_el_punto_es_separador_de_miles_no_decimal(self) -> None:
        """Interpretarlo como decimal convertiria 175.000,00 en 17.500.000."""
        assert normalizar_valor_monetario('"$175.000,00"') == 175_000.0
        assert normalizar_valor_monetario('"$175.000,00"') != 17_500_000.0

    @pytest.mark.parametrize("texto", ["", "   ", '""', "sin numero", None])
    def test_devuelve_none_cuando_no_hay_numero(self, texto) -> None:
        assert normalizar_valor_monetario(texto) is None


class TestExtraerMonto:
    """La clave `monto` hay que hallarla dentro de un JSON roto."""

    def test_extrae_de_una_estructura_con_llave_sin_cerrar(self) -> None:
        crudo = (
            '"[{account_name": "account_wwlcytqr", "delay_auto_settle": "1800", '
            '"monto": 1250000, "vtex_transaction_id": "I22H7JQ}]"'
        )
        assert extraer_monto(crudo) == 1_250_000.0

    def test_extrae_pese_a_escapes_sobrantes_en_la_clave(self) -> None:
        crudo = '[{account_name": "x", "monto\\": 165000, "vtex_transaction_id": "A"}]""'
        assert extraer_monto(crudo) == 165_000.0

    def test_con_clave_repetida_gana_la_ultima(self) -> None:
        """Semantica estandar de JSON. Es el caso real de TRX0138."""
        crudo = '{"monto": "410.000 COP", "monto": 1720000, "vtex": "W31"}'
        assert extraer_montos(crudo) == [410_000.0, 1_720_000.0]
        assert extraer_monto(crudo) == 1_720_000.0

    def test_clave_repetida_con_el_mismo_valor_no_es_un_problema(self) -> None:
        crudo = '{"monto": "188.000 COP", "monto": 188000}'
        assert extraer_monto(crudo) == 188_000.0

    def test_sin_clave_monto_devuelve_none(self) -> None:
        assert extraer_monto('{"account_name": "x"}') is None

    def test_campo_vacio_devuelve_none(self) -> None:
        assert extraer_monto("") is None
        assert extraer_montos("") == []
