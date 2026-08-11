"""Lee la tabla `Contabilizaciones`.

Es la fuente comoda: los campos ya vienen limpios. Aporta dos cosas que ninguna
otra tiene, el centro de costo y un estado que puede ser `PENDIENTE` o
`RECHAZADO`, que es justo lo que define la discrepancia de estado.

La abro en modo solo lectura a proposito. Es una fuente de datos, no el almacen
de la aplicacion: no hay ninguna razon para poder escribir en ella.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List

from reconciliacion.config import rutas
from reconciliacion.dominio.modelos import ESTADOS_VALIDOS_SQLITE, Contabilizacion
from reconciliacion.errores import FuenteCorruptaError
from reconciliacion.limpieza.fechas import parsear_fecha
from reconciliacion.loaders.base import CargadorFuente, ResultadoCarga

#: Columnas que se leen de la tabla de contabilizaciones.
CONSULTA = (
    "SELECT Referencia, Monto, Fecha, Centro_Costo, Estado, Banco, Marca "
    "FROM {tabla}"
)


class CargadorContabilizaciones(CargadorFuente[Contabilizacion]):
    """Lee los registros contabilizados de la base SQLite."""

    nombre = "Contabilizaciones (SQLite)"

    def __init__(self, ruta: Path | None = None, tabla: str | None = None) -> None:
        """Crea el cargador.

        Args:
            ruta: Ruta del archivo `.db`. Si se omite se usa la de `rutas`.
            tabla: Nombre de la tabla. Si se omite se usa la de `rutas`.
        """
        super().__init__(ruta or rutas.RUTA_DB_CONTABILIZACIONES)
        self.tabla = tabla or rutas.TABLA_CONTABILIZACIONES

    def _clave(self, registro: Contabilizacion) -> str:
        """Devuelve el identificador de transaccion del registro."""
        return registro.id_transaccion

    def _leer(self) -> ResultadoCarga[Contabilizacion]:
        """Lee la tabla de contabilizaciones completa.

        Returns:
            Los registros contables encontrados.

        Raises:
            FuenteCorruptaError: Si la base no se puede abrir o la tabla no
                existe con la estructura esperada.
        """
        registros: List[Contabilizacion] = []
        advertencias: List[str] = []
        leidos = 0

        # Solo lectura: la base de datos es una fuente, nunca se modifica.
        uri = f"file:{self.ruta.as_posix()}?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True) as conexion:
                conexion.row_factory = sqlite3.Row
                for fila in conexion.execute(CONSULTA.format(tabla=self.tabla)):
                    leidos += 1
                    identificador = (fila["Referencia"] or "").strip()
                    if not identificador:
                        advertencias.append("Registro sin Referencia; se descarta.")
                        continue

                    fecha = parsear_fecha(fila["Fecha"])
                    if fecha is None:
                        advertencias.append(
                            f"{identificador}: fecha ilegible ({fila['Fecha']!r})."
                        )

                    registros.append(
                        Contabilizacion(
                            id_transaccion=identificador,
                            monto=self._a_float(fila["Monto"]),
                            fecha=fecha,
                            centro_costo=(fila["Centro_Costo"] or "").strip(),
                            estado=(fila["Estado"] or "").strip().upper(),
                            banco=(fila["Banco"] or "").strip() or None,
                            marca=(fila["Marca"] or "").strip() or None,
                        )
                    )
        except sqlite3.Error as exc:
            raise FuenteCorruptaError(
                "No se pudo leer la base de datos de contabilizaciones.",
                detalle=str(exc),
            ) from exc

        advertencias.extend(
            self._validar_vocabulario(
                (r.estado for r in registros), ESTADOS_VALIDOS_SQLITE, "estado"
            )
        )

        return ResultadoCarga(
            fuente=self.nombre,
            registros=registros,
            advertencias=advertencias,
            registros_leidos=leidos,
        )

    @staticmethod
    def _a_float(valor: object) -> float | None:
        """Convierte el monto a `float` sin lanzar si el dato viniera sucio."""
        try:
            return float(valor)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
