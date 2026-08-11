"""El molde de los tres cargadores.

Las fuentes no se parecen en nada —un CSV roto, una base SQLite, un JSON— pero el
resto del sistema no tiene por que enterarse. Aqui fijo los cuatro pasos que son
iguales para todas y dejo que cada una implemente solo el que cambia:

1. comprobar que el archivo esta
2. leerlo                          <- lo unico especifico de cada fuente
3. validar lo leido
4. devolver siempre la misma estructura

Agregar una cuarta fuente manana es escribir un `_leer` y nada mas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Collection, Generic, Iterable, List, Sequence, TypeVar

from reconciliacion.errores import FuenteNoDisponibleError
from reconciliacion.log import obtener_logger

T = TypeVar("T")

_log = obtener_logger(__name__)


@dataclass
class ResultadoCarga(Generic[T]):
    """Resultado uniforme de cargar una fuente.

    Attributes:
        fuente: Nombre legible de la fuente.
        registros: Registros ya convertidos al modelo del dominio.
        advertencias: Problemas de integridad detectados que no impiden
            continuar (ids duplicados, montos ausentes, fechas ilegibles...).
        registros_leidos: Cuantos registros trajo el archivo antes de validar.
            Comparado con `len(registros)` permite demostrar que no se perdio
            ninguna fila en silencio.
    """

    fuente: str
    registros: List[T] = field(default_factory=list)
    advertencias: List[str] = field(default_factory=list)
    registros_leidos: int = 0

    @property
    def total(self) -> int:
        """Cantidad de registros validos cargados."""
        return len(self.registros)

    @property
    def hubo_perdida(self) -> bool:
        """Indica si se descarto algun registro respecto a lo leido."""
        return self.registros_leidos != self.total


class CargadorFuente(ABC, Generic[T]):
    """Cargador abstracto de una fuente de datos.

    Attributes:
        nombre: Nombre legible de la fuente, usado en logs y en la interfaz.
        ruta: Ubicacion del archivo en disco.
    """

    nombre: str = "fuente"

    def __init__(self, ruta: Path) -> None:
        """Crea el cargador.

        Args:
            ruta: Ruta del archivo a leer.
        """
        self.ruta = Path(ruta)

    def cargar(self) -> ResultadoCarga[T]:
        """Carga la fuente completa: lectura + validacion de integridad.

        Returns:
            El resultado de la carga con registros y advertencias.

        Raises:
            FuenteNoDisponibleError: Si el archivo no existe.
            FuenteCorruptaError: Si el archivo no se puede interpretar.
        """
        self._verificar_existencia()
        _log.info("Cargando %s desde %s", self.nombre, self.ruta.name)

        resultado = self._leer()
        resultado.advertencias.extend(self._validar_integridad(resultado.registros))

        _log.info(
            "%s: %d registros cargados (%d leidos, %d advertencias)",
            self.nombre,
            resultado.total,
            resultado.registros_leidos,
            len(resultado.advertencias),
        )
        for advertencia in resultado.advertencias:
            _log.warning("%s: %s", self.nombre, advertencia)
        return resultado

    def _verificar_existencia(self) -> None:
        """Comprueba que el archivo de la fuente este en disco.

        Raises:
            FuenteNoDisponibleError: Si no existe o no es un archivo.
        """
        if not self.ruta.is_file():
            raise FuenteNoDisponibleError(
                f"No se encontro el archivo de {self.nombre}.",
                detalle=f"Ruta esperada: {self.ruta}",
            )

    @abstractmethod
    def _leer(self) -> ResultadoCarga[T]:
        """Lee el archivo y construye los registros. Lo implementa cada fuente."""

    @abstractmethod
    def _clave(self, registro: T) -> str:
        """Devuelve el identificador de transaccion de un registro."""

    def _validar_integridad(self, registros: Sequence[T]) -> List[str]:
        """Valida reglas de integridad comunes a todas las fuentes.

        Comprueba que ningun registro venga sin identificador y que la llave de
        cruce sea unica dentro de la fuente: un id repetido rompe el cruce
        posterior, asi que debe quedar reportado.

        Args:
            registros: Registros ya construidos.

        Returns:
            Lista de advertencias legibles (vacia si todo esta correcto).
        """
        advertencias: List[str] = []

        sin_id = sum(1 for r in registros if not self._clave(r))
        if sin_id:
            advertencias.append(f"{sin_id} registro(s) sin identificador de transaccion.")

        repetidos = [
            clave
            for clave, veces in Counter(self._clave(r) for r in registros).items()
            if clave and veces > 1
        ]
        if repetidos:
            muestra = ", ".join(sorted(repetidos)[:5])
            advertencias.append(
                f"{len(repetidos)} identificador(es) duplicado(s): {muestra}"
                f"{'...' if len(repetidos) > 5 else ''}"
            )
        return advertencias

    @staticmethod
    def _validar_vocabulario(
        valores: Iterable[str], admitidos: Collection[str], campo: str
    ) -> List[str]:
        """Comprueba que un campo solo traiga valores del catalogo esperado.

        Un valor fuera del catalogo no es una discrepancia de negocio: es un
        dato que el sistema no sabe interpretar y que, si se ignora, termina en
        una clasificacion silenciosamente equivocada.

        Args:
            valores: Valores hallados en la fuente.
            admitidos: Valores permitidos para ese campo.
            campo: Nombre del campo, para redactar el mensaje.

        Returns:
            Una advertencia por cada valor inesperado, con su frecuencia.
        """
        inesperados = Counter(valor for valor in valores if valor and valor not in admitidos)
        return [
            f"{veces} registro(s) con {campo} inesperado: {valor!r} "
            f"(se esperaba {' / '.join(sorted(admitidos))})."
            for valor, veces in inesperados.items()
        ]
