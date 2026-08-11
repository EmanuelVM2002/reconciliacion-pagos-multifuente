"""Carga de `autorizaciones.csv` (lo que se autorizo).

Este loader se limita a **leer**: devuelve las filas tal cual vienen del
archivo, sin interpretar los campos malformados. La extraccion del monto, la
marca y las retenciones es responsabilidad del paquete `limpieza`.

Esa separacion es deliberada: permite probar el parseo de los campos sucios
con cadenas de texto en los tests, sin necesidad de un archivo en disco.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from reconciliacion.config import rutas
from reconciliacion.dominio.modelos import FilaAutorizacionCruda
from reconciliacion.errores import FuenteCorruptaError
from reconciliacion.loaders.base import CargadorFuente, ResultadoCarga

#: Separador de columnas del archivo de autorizaciones.
DELIMITADOR = ";"

#: Columnas que el archivo debe traer si o si.
COLUMNAS_REQUERIDAS = ("ID_Transaccion", "Monto", "Fecha", "Banco", "Marca", "Estado")


class CargadorAutorizaciones(CargadorFuente[FilaAutorizacionCruda]):
    """Lee las autorizaciones del CSV como filas crudas."""

    nombre = "Autorizaciones (CSV)"

    def __init__(self, ruta: Path | None = None) -> None:
        """Crea el cargador.

        Args:
            ruta: Ruta del CSV. Si se omite se usa la configurada en `rutas`.
        """
        super().__init__(ruta or rutas.RUTA_CSV_AUTORIZACIONES)

    def _clave(self, registro: FilaAutorizacionCruda) -> str:
        """Devuelve el identificador de transaccion de la fila."""
        return registro.id_transaccion

    def _leer(self) -> ResultadoCarga[FilaAutorizacionCruda]:
        """Lee el CSV completo.

        Returns:
            Las filas crudas del archivo.

        Raises:
            FuenteCorruptaError: Si el archivo no tiene las columnas esperadas
                o no se puede decodificar.
        """
        filas: List[FilaAutorizacionCruda] = []
        advertencias: List[str] = []
        leidas = 0

        try:
            with self.ruta.open("r", encoding="utf-8", newline="") as archivo:
                lector = csv.DictReader(archivo, delimiter=DELIMITADOR)
                self._verificar_columnas(lector.fieldnames)

                # start=2 porque la fila 1 del archivo son los encabezados.
                for numero, fila in enumerate(lector, start=2):
                    leidas += 1
                    identificador = (fila.get("ID_Transaccion") or "").strip()
                    if not identificador:
                        advertencias.append(f"Fila {numero} sin ID_Transaccion; se descarta.")
                        continue
                    filas.append(
                        FilaAutorizacionCruda(
                            id_transaccion=identificador,
                            monto_crudo=fila.get("Monto") or "",
                            fecha_cruda=(fila.get("Fecha") or "").strip(),
                            banco=(fila.get("Banco") or "").strip(),
                            marca_cruda=fila.get("Marca") or "",
                            estado=(fila.get("Estado") or "").strip(),
                            numero_fila=numero,
                        )
                    )
        except UnicodeDecodeError as exc:
            raise FuenteCorruptaError(
                "El archivo de autorizaciones tiene una codificacion no valida.",
                detalle=str(exc),
            ) from exc
        except csv.Error as exc:
            raise FuenteCorruptaError(
                "El archivo de autorizaciones no se pudo leer como CSV.",
                detalle=str(exc),
            ) from exc

        return ResultadoCarga(
            fuente=self.nombre,
            registros=filas,
            advertencias=advertencias,
            registros_leidos=leidas,
        )

    @staticmethod
    def _verificar_columnas(encabezados: List[str] | None) -> None:
        """Valida que el CSV traiga las columnas requeridas.

        Args:
            encabezados: Nombres de columna leidos del archivo.

        Raises:
            FuenteCorruptaError: Si falta alguna columna obligatoria.
        """
        presentes = set(encabezados or ())
        faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in presentes]
        if faltantes:
            raise FuenteCorruptaError(
                "El archivo de autorizaciones no tiene las columnas esperadas.",
                detalle=f"Faltan: {', '.join(faltantes)}",
            )
