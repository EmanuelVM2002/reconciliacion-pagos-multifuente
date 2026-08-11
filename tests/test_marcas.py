"""Pruebas de la extraccion y normalizacion de la marca."""

from __future__ import annotations

import pytest

from reconciliacion.limpieza.marcas import (
    extraer_marca,
    marcas_coinciden,
    normalizar_marca,
    primera_no_vacia,
)


class TestExtraerMarca:
    """La marca viaja como ultimo elemento de la lista de retenciones."""

    def test_extrae_de_una_lista_de_retenciones(self) -> None:
        crudo = (
            '[{"financial_entity": "iva", "amount": "-4936.72"}, '
            '{"marca": "NAF NAF"}}]""'
        )
        assert extraer_marca(crudo) == "NAF NAF"

    def test_extrae_pese_a_escapes_sobrantes(self) -> None:
        assert extraer_marca('[{"marca\\": "CHEVIGNON"}]"') == "CHEVIGNON"

    def test_extrae_marcas_de_dos_palabras(self) -> None:
        assert extraer_marca('[{"marca": "AMERICAN EAGLE"}]') == "AMERICAN EAGLE"

    def test_sin_marca_devuelve_none(self) -> None:
        assert extraer_marca('[{"financial_entity": "iva"}]') is None
        assert extraer_marca("") is None


class TestNormalizarMarca:
    """La regla es quedarse con el primer token (ver README)."""

    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("NAF NAF", "NAF"),
            ("AMERICAN EAGLE", "AMERICAN"),
            ("AMERICANINO", "AMERICANINO"),
            ("CHEVIGNON", "CHEVIGNON"),
            ("RIFLE", "RIFLE"),
        ],
    )
    def test_normaliza_al_primer_token(self, entrada: str, esperado: str) -> None:
        assert normalizar_marca(entrada) == esperado

    def test_ignora_mayusculas_tildes_y_espacios_de_sobra(self) -> None:
        assert normalizar_marca("  chévignon  ") == "CHEVIGNON"

    def test_no_colisiona_americanino_con_american_eagle(self) -> None:
        """Si colisionaran, la regla del primer token no seria valida."""
        assert normalizar_marca("AMERICANINO") != normalizar_marca("AMERICAN EAGLE")

    @pytest.mark.parametrize("entrada", ["", "   ", None, "---"])
    def test_devuelve_none_si_no_queda_nada(self, entrada) -> None:
        assert normalizar_marca(entrada) is None


class TestMarcasCoinciden:
    """Es la comparacion que alimenta la columna Marca_Coincide."""

    def test_coinciden_pese_a_escribirse_distinto(self) -> None:
        assert marcas_coinciden("NAF NAF", "NAF", "NAF") is True
        assert marcas_coinciden("AMERICAN EAGLE", "AMERICAN", "AMERICAN") is True

    def test_detecta_marcas_realmente_distintas(self) -> None:
        assert marcas_coinciden("CHEVIGNON", "RIFLE", "RIFLE") is False

    def test_ignora_las_fuentes_ausentes(self) -> None:
        assert marcas_coinciden("NAF NAF", None, "NAF") is True

    def test_sin_ninguna_marca_no_hay_nada_que_comparar(self) -> None:
        assert marcas_coinciden(None, None, None) is None


def test_primera_no_vacia() -> None:
    assert primera_no_vacia([None, "", "BANCO_A", "BANCO_B"]) == "BANCO_A"
    assert primera_no_vacia([None, ""]) is None
