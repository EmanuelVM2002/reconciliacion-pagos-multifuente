"""Cargadores de las tres fuentes de datos."""

from reconciliacion.loaders.base import CargadorFuente, ResultadoCarga
from reconciliacion.loaders.csv_loader import CargadorAutorizaciones
from reconciliacion.loaders.json_loader import CargadorMovimientos
from reconciliacion.loaders.sqlite_loader import CargadorContabilizaciones

__all__ = [
    "CargadorAutorizaciones",
    "CargadorContabilizaciones",
    "CargadorFuente",
    "CargadorMovimientos",
    "ResultadoCarga",
]
