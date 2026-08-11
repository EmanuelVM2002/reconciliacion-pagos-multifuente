"""Utilidades compartidas por las pruebas.

Construir un modelo del dominio a mano en cada prueba es ruidoso y esconde lo
que la prueba realmente quiere afirmar. Estas fabricas dejan explicito solo lo
que importa en cada caso y ponen valores razonables en el resto.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

import pytest

from reconciliacion.dominio.modelos import (
    Autorizacion,
    Contabilizacion,
    FilaAutorizacionCruda,
    MovimientoBancario,
    Retencion,
)
from reconciliacion.dominio.transaccion import TransaccionReconciliada

FECHA = datetime(2026, 7, 15, 14, 30)


@pytest.fixture
def fabricar_autorizacion():
    """Devuelve una fabrica de autorizaciones con valores por defecto."""

    def _fabricar(
        id_transaccion: str = "TRX0001",
        monto: Optional[float] = 100_000.0,
        fecha: Optional[datetime] = FECHA,
        banco: str = "BANCO_A",
        marca: Optional[str] = "CHEVIGNON",
        estado: str = "AUTORIZADO",
        retenciones: Optional[Sequence[Retencion]] = None,
    ) -> Autorizacion:
        return Autorizacion(
            id_transaccion=id_transaccion,
            monto=monto,
            fecha=fecha,
            banco=banco,
            marca=marca,
            estado=estado,
            retenciones=list(retenciones or []),
        )

    return _fabricar


@pytest.fixture
def fabricar_contabilizacion():
    """Devuelve una fabrica de contabilizaciones con valores por defecto."""

    def _fabricar(
        id_transaccion: str = "TRX0001",
        monto: Optional[float] = 100_000.0,
        fecha: Optional[datetime] = FECHA,
        centro_costo: str = "POS001",
        estado: str = "CONTABILIZADO",
        banco: Optional[str] = "BANCO_A",
        marca: Optional[str] = "CHEVIGNON",
    ) -> Contabilizacion:
        return Contabilizacion(
            id_transaccion=id_transaccion,
            monto=monto,
            fecha=fecha,
            centro_costo=centro_costo,
            estado=estado,
            banco=banco,
            marca=marca,
        )

    return _fabricar


@pytest.fixture
def fabricar_movimiento():
    """Devuelve una fabrica de movimientos bancarios con valores por defecto."""

    def _fabricar(
        id_transaccion: str = "TRX0001",
        monto: Optional[float] = 100_000.0,
        fecha: Optional[datetime] = FECHA,
        id_movimiento: str = "MOV0001",
        banco: Optional[str] = "BANCO_A",
        estado: str = "COMPLETADO",
        marca: Optional[str] = "CHEVIGNON",
    ) -> MovimientoBancario:
        return MovimientoBancario(
            id_movimiento=id_movimiento,
            id_transaccion=id_transaccion,
            monto=monto,
            fecha=fecha,
            banco=banco,
            estado=estado,
            marca=marca,
        )

    return _fabricar


@pytest.fixture
def fabricar_transaccion(fabricar_autorizacion, fabricar_contabilizacion, fabricar_movimiento):
    """Devuelve una fabrica de transacciones presentes en las tres fuentes."""

    def _fabricar(
        id_transaccion: str = "TRX0001",
        en_csv: bool = True,
        en_sqlite: bool = True,
        en_json: bool = True,
        **valores,
    ) -> TransaccionReconciliada:
        comunes = {"id_transaccion": id_transaccion}
        return TransaccionReconciliada(
            id_transaccion=id_transaccion,
            autorizacion=fabricar_autorizacion(
                **comunes, **{k[4:]: v for k, v in valores.items() if k.startswith("csv_")}
            )
            if en_csv
            else None,
            contabilizacion=fabricar_contabilizacion(
                **comunes, **{k[4:]: v for k, v in valores.items() if k.startswith("sql_")}
            )
            if en_sqlite
            else None,
            movimiento=fabricar_movimiento(
                **comunes, **{k[5:]: v for k, v in valores.items() if k.startswith("json_")}
            )
            if en_json
            else None,
        )

    return _fabricar


@pytest.fixture
def fabricar_fila_cruda():
    """Devuelve una fabrica de filas crudas del CSV."""

    def _fabricar(
        id_transaccion: str = "TRX0001",
        monto_crudo: str = '{"monto": 100000}',
        fecha_cruda: str = "15/07/2026 14:30",
        banco: str = "BANCO_A",
        marca_cruda: str = '[{"marca": "CHEVIGNON"}]',
        estado: str = "AUTORIZADO",
        numero_fila: int = 2,
    ) -> FilaAutorizacionCruda:
        return FilaAutorizacionCruda(
            id_transaccion=id_transaccion,
            monto_crudo=monto_crudo,
            fecha_cruda=fecha_cruda,
            banco=banco,
            marca_cruda=marca_cruda,
            estado=estado,
            numero_fila=numero_fila,
        )

    return _fabricar
