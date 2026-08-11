"""Carga de `movimientos_bancarios.json` (lo que llego al banco).

Cada movimiento trae su propio identificador (`MOVxxxx`) ademas de la
referencia a la transaccion (`transaccion_id`), que es la llave de cruce.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from reconciliacion.config import rutas
from reconciliacion.dominio.modelos import ESTADOS_VALIDOS_JSON, MovimientoBancario
from reconciliacion.errores import FuenteCorruptaError
from reconciliacion.limpieza.fechas import parsear_fecha
from reconciliacion.loaders.base import CargadorFuente, ResultadoCarga


class CargadorMovimientos(CargadorFuente[MovimientoBancario]):
    """Lee los movimientos reportados por el banco."""

    nombre = "Movimientos bancarios (JSON)"

    def __init__(self, ruta: Path | None = None) -> None:
        """Crea el cargador.

        Args:
            ruta: Ruta del archivo JSON. Si se omite se usa la de `rutas`.
        """
        super().__init__(ruta or rutas.RUTA_JSON_MOVIMIENTOS)

    def _clave(self, registro: MovimientoBancario) -> str:
        """Devuelve el identificador de transaccion del movimiento."""
        return registro.id_transaccion

    def _leer(self) -> ResultadoCarga[MovimientoBancario]:
        """Lee el archivo de movimientos bancarios.

        Returns:
            Los movimientos encontrados.

        Raises:
            FuenteCorruptaError: Si el JSON es invalido o no es una lista de
                objetos.
        """
        try:
            contenido = json.loads(self.ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FuenteCorruptaError(
                "El archivo de movimientos bancarios no es un JSON valido.",
                detalle=f"Linea {exc.lineno}, columna {exc.colno}: {exc.msg}",
            ) from exc
        except UnicodeDecodeError as exc:
            raise FuenteCorruptaError(
                "El archivo de movimientos bancarios tiene una codificacion no valida.",
                detalle=str(exc),
            ) from exc

        if not isinstance(contenido, list):
            raise FuenteCorruptaError(
                "El archivo de movimientos bancarios no contiene una lista de movimientos.",
                detalle=f"Tipo encontrado: {type(contenido).__name__}",
            )

        registros: List[MovimientoBancario] = []
        advertencias: List[str] = []

        for posicion, crudo in enumerate(contenido, start=1):
            if not isinstance(crudo, dict):
                advertencias.append(f"Movimiento #{posicion} no es un objeto; se descarta.")
                continue

            identificador = str(crudo.get("transaccion_id") or "").strip()
            if not identificador:
                advertencias.append(
                    f"Movimiento {crudo.get('id', f'#{posicion}')} sin transaccion_id; se descarta."
                )
                continue

            fecha = parsear_fecha(crudo.get("fecha"))
            if fecha is None:
                advertencias.append(f"{identificador}: fecha ilegible ({crudo.get('fecha')!r}).")

            registros.append(
                MovimientoBancario(
                    id_movimiento=str(crudo.get("id") or "").strip(),
                    id_transaccion=identificador,
                    monto=self._a_float(crudo.get("monto")),
                    fecha=fecha,
                    banco=self._texto(crudo, "banco"),
                    estado=(str(crudo.get("estado") or "").strip().upper()),
                    marca=self._texto(crudo, "marca"),
                )
            )

        advertencias.extend(
            self._validar_vocabulario(
                (r.estado for r in registros), ESTADOS_VALIDOS_JSON, "estado"
            )
        )

        return ResultadoCarga(
            fuente=self.nombre,
            registros=registros,
            advertencias=advertencias,
            registros_leidos=len(contenido),
        )

    @staticmethod
    def _texto(crudo: Dict[str, Any], clave: str) -> str | None:
        """Devuelve un campo de texto normalizado, o `None` si viene vacio."""
        valor = str(crudo.get(clave) or "").strip()
        return valor or None

    @staticmethod
    def _a_float(valor: object) -> float | None:
        """Convierte el monto a `float` sin lanzar si el dato viniera sucio."""
        try:
            return float(valor)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
