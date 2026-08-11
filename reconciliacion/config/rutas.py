"""Configuracion centralizada de rutas del proyecto.

Este modulo es la unica fuente de verdad sobre donde viven los archivos de
entrada y de salida. La prueba pide explicitamente que no haya selectores de
archivo en la interfaz: la GUI y el script de consola leen las rutas de aqui.

Las rutas se resuelven de forma relativa a la raiz del repositorio, de modo que
el proyecto funciona sin cambios en cualquier maquina o carpeta.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

# Raiz del repositorio: .../reconciliacion-pagos
RAIZ_PROYECTO: Path = Path(__file__).resolve().parents[2]

# --- Entradas -------------------------------------------------------------
DIRECTORIO_DATOS: Path = RAIZ_PROYECTO / "datos"

RUTA_CSV_AUTORIZACIONES: Path = DIRECTORIO_DATOS / "autorizaciones.csv"
RUTA_DB_CONTABILIZACIONES: Path = DIRECTORIO_DATOS / "reconciliacion_pagos.db"
RUTA_JSON_MOVIMIENTOS: Path = DIRECTORIO_DATOS / "movimientos_bancarios.json"

# --- Salidas --------------------------------------------------------------
DIRECTORIO_SALIDA: Path = RAIZ_PROYECTO / "salida"
NOMBRE_REPORTE: str = "reporte_reconciliacion.xlsx"
RUTA_REPORTE_EXCEL: Path = DIRECTORIO_SALIDA / NOMBRE_REPORTE

# --- Parametros de la base de datos --------------------------------------
TABLA_CONTABILIZACIONES: str = "Contabilizaciones"

# Nombre legible de cada fuente -> ruta esperada. Se usa para reportar en la
# interfaz que archivo falta, con el nombre que entiende una persona de
# contabilidad y no con la ruta cruda.
FUENTES_REQUERIDAS: Dict[str, Path] = {
    "Autorizaciones (CSV)": RUTA_CSV_AUTORIZACIONES,
    "Contabilizaciones (SQLite)": RUTA_DB_CONTABILIZACIONES,
    "Movimientos bancarios (JSON)": RUTA_JSON_MOVIMIENTOS,
}


def asegurar_directorio_salida() -> Path:
    """Crea la carpeta de salida si no existe y devuelve su ruta."""
    DIRECTORIO_SALIDA.mkdir(parents=True, exist_ok=True)
    return DIRECTORIO_SALIDA


def fuentes_faltantes() -> List[str]:
    """Devuelve los nombres legibles de las fuentes que no estan en disco.

    Returns:
        Lista vacia si las tres fuentes existen; en caso contrario, los nombres
        de las que faltan, listos para mostrarse al usuario final.
    """
    return [nombre for nombre, ruta in FUENTES_REQUERIDAS.items() if not ruta.is_file()]
