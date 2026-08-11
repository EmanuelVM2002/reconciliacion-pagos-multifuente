"""Pruebas de la extraccion de retenciones y de las tres sumas del reporte."""

from __future__ import annotations

from reconciliacion.dominio.modelos import Retencion
from reconciliacion.limpieza.retenciones import (
    entidades_desconocidas,
    extraer_retenciones,
    totalizar_por_entidad,
)

CAMPO_REAL = (
    '[{"financial_entity": "aumento", "amount": "-139.24", "detail": "tax_withholding"}, '
    '{"financial_entity": "aumento", "amount": "-2758.42", "detail": "tax_withholding"}, '
    '{"financial_entity": "ica", "amount": "-3071.19", "detail": "tax_withholding"}, '
    '{"marca": "AMERICANINO"}}]""'
)


class TestExtraerRetenciones:
    """El campo trae varias variantes de corrupcion conviviendo."""

    def test_extrae_todas_las_retenciones_de_una_fila_real(self) -> None:
        retenciones = extraer_retenciones(CAMPO_REAL)
        assert len(retenciones) == 3
        assert [r.entidad for r in retenciones] == ["aumento", "aumento", "ica"]

    def test_conserva_el_signo_negativo(self) -> None:
        """El enunciado pide no convertir a positivo."""
        retenciones = extraer_retenciones(CAMPO_REAL)
        assert all(r.monto < 0 for r in retenciones)

    def test_conserva_las_ocurrencias_repetidas_de_una_entidad(self) -> None:
        retenciones = extraer_retenciones(CAMPO_REAL)
        aumentos = [r.monto for r in retenciones if r.entidad == "aumento"]
        assert aumentos == [-139.24, -2758.42]

    def test_extrae_pese_a_una_clave_duplicada_y_pegada(self) -> None:
        crudo = '[{financial_entityfinancial_entity": "fuente", "amount": "-3336.41"}]'
        assert extraer_retenciones(crudo) == [Retencion("fuente", -3336.41)]

    def test_no_cruza_la_entidad_de_una_con_el_monto_de_la_siguiente(self) -> None:
        crudo = (
            '[{"financial_entity": "iva"}, '
            '{"financial_entity": "ica", "amount": "-100"}]'
        )
        assert extraer_retenciones(crudo) == [Retencion("ica", -100.0)]

    def test_campo_sin_retenciones(self) -> None:
        assert extraer_retenciones('[{"marca": "RIFLE"}]') == []
        assert extraer_retenciones("") == []


class TestTotalizarPorEntidad:
    """Una entidad repetida suma todas sus ocurrencias."""

    def test_suma_las_ocurrencias_repetidas(self) -> None:
        totales = totalizar_por_entidad(extraer_retenciones(CAMPO_REAL))
        assert totales["aumento"] == -2897.66
        assert totales["ica"] == -3071.19

    def test_solo_incluye_las_entidades_presentes(self) -> None:
        totales = totalizar_por_entidad(extraer_retenciones(CAMPO_REAL))
        assert "iva" not in totales


class TestSumasDelReporte:
    """Las tres columnas de retenciones, con entidad ausente valiendo 0."""

    def test_entidad_ausente_vale_cero(self, fabricar_autorizacion) -> None:
        autorizacion = fabricar_autorizacion(
            retenciones=[Retencion("iva", -100.0)]  # sin ica ni fuente
        )
        assert autorizacion.total_retencion("iva", "ica") == -100.0
        assert autorizacion.total_retencion("fuente", "iva") == -100.0
        assert autorizacion.total_retencion("iva", "ica", "fuente") == -100.0

    def test_suma_las_tres_combinaciones(self, fabricar_autorizacion) -> None:
        autorizacion = fabricar_autorizacion(
            retenciones=[
                Retencion("iva", -100.0),
                Retencion("ica", -50.0),
                Retencion("fuente", -25.0),
            ]
        )
        assert autorizacion.total_retencion("iva", "ica") == -150.0
        assert autorizacion.total_retencion("fuente", "iva") == -125.0
        assert autorizacion.total_retencion("iva", "ica", "fuente") == -175.0

    def test_cree_y_aumento_no_entran_en_las_sumas(self, fabricar_autorizacion) -> None:
        autorizacion = fabricar_autorizacion(
            retenciones=[
                Retencion("iva", -100.0),
                Retencion("cree", -999.0),
                Retencion("aumento", -888.0),
            ]
        )
        assert autorizacion.total_retencion("iva", "ica", "fuente") == -100.0

    def test_sin_retenciones_la_suma_es_cero(self, fabricar_autorizacion) -> None:
        assert fabricar_autorizacion(retenciones=[]).total_retencion("iva", "ica") == 0.0


def test_entidades_desconocidas_se_reportan() -> None:
    """Una entidad nueva no puede pasar desapercibida."""
    conocidas = [Retencion("iva", -1.0), Retencion("cree", -2.0)]
    assert entidades_desconocidas(conocidas) == []
    assert entidades_desconocidas(conocidas + [Retencion("rete_otro", -3.0)]) == ["rete_otro"]
