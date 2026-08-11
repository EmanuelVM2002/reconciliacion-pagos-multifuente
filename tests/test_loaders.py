"""Pruebas de los cargadores y de la validacion de integridad.

Se escriben archivos temporales en vez de usar los datos reales, para poder
provocar a voluntad los casos que en produccion no se pueden reproducir: un
archivo que falta, un JSON invalido, una tabla sin las columnas esperadas.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from reconciliacion.errores import FuenteCorruptaError, FuenteNoDisponibleError
from reconciliacion.limpieza.fechas import parsear_fecha
from reconciliacion.loaders import (
    CargadorAutorizaciones,
    CargadorContabilizaciones,
    CargadorMovimientos,
)

CSV_MINIMO = (
    "ID_Transaccion;Monto;Fecha;Banco;Marca;Estado\n"
    'TRX0001;{"monto": 100000};15/07/2026 14:30;BANCO_A;[{"marca": "RIFLE"}];AUTORIZADO\n'
    'TRX0002;{"monto": 200000};16/07/2026 9:00;BANCO_B;[{"marca": "NAF NAF"}];AUTORIZADO\n'
)


@pytest.fixture
def csv_temporal(tmp_path: Path) -> Path:
    ruta = tmp_path / "autorizaciones.csv"
    ruta.write_text(CSV_MINIMO, encoding="utf-8")
    return ruta


@pytest.fixture
def db_temporal(tmp_path: Path) -> Path:
    ruta = tmp_path / "pagos.db"
    conexion = sqlite3.connect(ruta)
    conexion.execute(
        "CREATE TABLE Contabilizaciones (ID INTEGER PRIMARY KEY, Referencia TEXT, "
        "Monto REAL, Fecha TEXT, Centro_Costo TEXT, Estado TEXT, Banco TEXT, Marca TEXT)"
    )
    conexion.execute(
        "INSERT INTO Contabilizaciones VALUES "
        "(1, 'TRX0001', 100000.0, '15/07/2026 14:30', 'POS001', 'CONTABILIZADO', 'BANCO_A', 'RIFLE')"
    )
    conexion.commit()
    conexion.close()
    return ruta


@pytest.fixture
def json_temporal(tmp_path: Path) -> Path:
    ruta = tmp_path / "movimientos.json"
    ruta.write_text(
        json.dumps(
            [
                {
                    "id": "MOV0001",
                    "monto": 100000.0,
                    "fecha": "2026-07-15 14:30:00",
                    "banco": "BANCO_A",
                    "transaccion_id": "TRX0001",
                    "estado": "COMPLETADO",
                    "marca": "RIFLE",
                }
            ]
        ),
        encoding="utf-8",
    )
    return ruta


class TestCargadorAutorizaciones:
    def test_lee_las_filas_sin_interpretarlas(self, csv_temporal: Path) -> None:
        resultado = CargadorAutorizaciones(csv_temporal).cargar()
        assert resultado.total == 2
        assert resultado.hubo_perdida is False
        assert resultado.registros[0].id_transaccion == "TRX0001"
        assert '"monto": 100000' in resultado.registros[0].monto_crudo

    def test_conserva_el_numero_de_fila_para_trazar(self, csv_temporal: Path) -> None:
        registros = CargadorAutorizaciones(csv_temporal).cargar().registros
        assert registros[0].numero_fila == 2  # la 1 son los encabezados

    def test_archivo_inexistente(self, tmp_path: Path) -> None:
        with pytest.raises(FuenteNoDisponibleError) as error:
            CargadorAutorizaciones(tmp_path / "no_existe.csv").cargar()
        assert "Autorizaciones" in error.value.mensaje

    def test_columnas_faltantes(self, tmp_path: Path) -> None:
        ruta = tmp_path / "malo.csv"
        ruta.write_text("ID_Transaccion;Monto\nTRX0001;1\n", encoding="utf-8")
        with pytest.raises(FuenteCorruptaError) as error:
            CargadorAutorizaciones(ruta).cargar()
        assert "Fecha" in error.value.detalle

    def test_fila_sin_identificador_se_reporta(self, tmp_path: Path) -> None:
        ruta = tmp_path / "hueco.csv"
        ruta.write_text(CSV_MINIMO + ";{};01/01/2026 0:00;BANCO_A;[];AUTORIZADO\n", encoding="utf-8")
        resultado = CargadorAutorizaciones(ruta).cargar()
        assert resultado.total == 2
        assert resultado.hubo_perdida is True
        assert any("sin ID_Transaccion" in a for a in resultado.advertencias)


class TestCargadorContabilizaciones:
    def test_lee_y_convierte_los_registros(self, db_temporal: Path) -> None:
        resultado = CargadorContabilizaciones(db_temporal).cargar()
        assert resultado.total == 1
        registro = resultado.registros[0]
        assert registro.id_transaccion == "TRX0001"
        assert registro.centro_costo == "POS001"
        assert registro.estado_es_ok is True

    def test_base_inexistente(self, tmp_path: Path) -> None:
        with pytest.raises(FuenteNoDisponibleError):
            CargadorContabilizaciones(tmp_path / "no_existe.db").cargar()

    def test_tabla_inexistente(self, db_temporal: Path) -> None:
        with pytest.raises(FuenteCorruptaError):
            CargadorContabilizaciones(db_temporal, tabla="NoExiste").cargar()


class TestCargadorMovimientos:
    def test_lee_los_movimientos(self, json_temporal: Path) -> None:
        resultado = CargadorMovimientos(json_temporal).cargar()
        assert resultado.total == 1
        assert resultado.registros[0].id_movimiento == "MOV0001"
        assert resultado.registros[0].id_transaccion == "TRX0001"

    def test_json_invalido(self, tmp_path: Path) -> None:
        ruta = tmp_path / "roto.json"
        ruta.write_text("[{no es json}]", encoding="utf-8")
        with pytest.raises(FuenteCorruptaError):
            CargadorMovimientos(ruta).cargar()

    def test_json_que_no_es_una_lista(self, tmp_path: Path) -> None:
        ruta = tmp_path / "objeto.json"
        ruta.write_text('{"id": "MOV0001"}', encoding="utf-8")
        with pytest.raises(FuenteCorruptaError):
            CargadorMovimientos(ruta).cargar()

    def test_movimiento_sin_transaccion_se_reporta(self, tmp_path: Path) -> None:
        ruta = tmp_path / "huerfano.json"
        ruta.write_text(json.dumps([{"id": "MOV0009", "monto": 1}]), encoding="utf-8")
        resultado = CargadorMovimientos(ruta).cargar()
        assert resultado.total == 0
        assert resultado.hubo_perdida is True


class TestValidacionDeIntegridad:
    """La llave de cruce tiene que ser unica dentro de cada fuente."""

    def test_detecta_identificadores_duplicados(self, tmp_path: Path) -> None:
        ruta = tmp_path / "duplicados.json"
        ruta.write_text(
            json.dumps(
                [
                    {"id": "MOV1", "transaccion_id": "TRX0001", "fecha": "2026-07-15 10:00:00"},
                    {"id": "MOV2", "transaccion_id": "TRX0001", "fecha": "2026-07-15 11:00:00"},
                ]
            ),
            encoding="utf-8",
        )
        resultado = CargadorMovimientos(ruta).cargar()
        assert any("duplicado" in a for a in resultado.advertencias)


class TestParsearFecha:
    """Cada fuente escribe la fecha a su manera."""

    def test_formato_del_csv_y_de_sqlite(self) -> None:
        assert parsear_fecha("26/07/2026 9:00").hour == 9

    def test_formato_iso_del_json(self) -> None:
        assert parsear_fecha("2026-07-26 09:00:00").day == 26

    def test_valor_ilegible_devuelve_none_sin_lanzar(self) -> None:
        assert parsear_fecha("ayer por la tarde") is None
        assert parsear_fecha("") is None
        assert parsear_fecha(None) is None
