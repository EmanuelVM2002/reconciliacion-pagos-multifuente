"""Script ejecutable: corre la reconciliacion completa y genera el Excel.

Uso:
    python main.py

Ejecuta la cadena entera —carga de las tres fuentes, validacion de integridad,
limpieza de los campos malformados, reconciliacion, deteccion de fraude y
exportacion— mostrando el avance por consola y un resumen al final.

Es la version de terminal del mismo proceso que ejecuta la interfaz grafica:
ambos llaman a `ServicioReconciliacion`, asi que no hay logica duplicada ni
riesgo de que uno quede desactualizado respecto al otro.
"""

from __future__ import annotations

import sys

from reconciliacion.errores import ErrorReconciliacion
from reconciliacion.log import configurar_consola
from reconciliacion.servicio import ResultadoProceso, ServicioReconciliacion


def _mostrar_progreso(mensaje: str, porcentaje: float) -> None:
    """Imprime el avance del proceso en la consola.

    Args:
        mensaje: Descripcion del paso actual.
        porcentaje: Avance acumulado, de 0 a 100.
    """
    print(f"[{porcentaje:5.1f}%] {mensaje}")


def _mostrar_resumen(resultado: ResultadoProceso) -> None:
    """Imprime los indicadores agregados de la ejecucion.

    Args:
        resultado: Resultado devuelto por el servicio.
    """
    resumen = resultado.resumen
    fraude = resultado.resumen_fraude

    print("\n" + "=" * 62)
    print("RESUMEN DE LA RECONCILIACION")
    print("=" * 62)

    for fuente, total in resultado.registros_por_fuente.items():
        print(f"  {fuente:<32} {total:>6} registros")

    if resultado.limpieza is not None:
        print(f"\n  Limpieza del CSV: {resultado.limpieza.resumen()}")

    print(f"\n  Universo (union de las 3 fuentes) {resumen.total:>6}")
    print(
        f"  Reconciliadas                    {resumen.reconciliadas:>6}"
        f"  ({resumen.porcentaje_reconciliacion:.1f}%)"
    )
    for etiqueta, veces in sorted(resumen.por_clasificacion.items(), key=lambda x: -x[1]):
        if etiqueta != "RECONCILIADO":
            print(f"  {etiqueta:<32} {veces:>6}")

    print(f"\n  Monto total                      ${resumen.monto_total:>15,.0f}")
    print(f"  Monto en discrepancia            ${resumen.monto_en_discrepancia:>15,.0f}")

    print(f"\n  Transacciones con fraude         {fraude.total_fraudes:>6}")
    for tipo, veces in sorted(fraude.por_tipo.items(), key=lambda x: -x[1]):
        print(f"  {tipo:<32} {veces:>6}")
    for nivel, veces in fraude.por_nivel.items():
        print(f"  Riesgo {nivel:<25} {veces:>6}")

    print(f"\n  Duracion                         {resultado.duracion_segundos:>6.2f} s")
    print(f"  Reporte generado en: {resultado.ruta_reporte}")
    print("=" * 62)


def main() -> int:
    """Punto de entrada del script.

    Returns:
        `0` si el proceso termino bien, `1` si fallo por un problema previsible
        (falta un archivo, una fuente esta corrupta, el Excel esta abierto).
    """
    configurar_consola()

    try:
        resultado = ServicioReconciliacion().ejecutar(progreso=_mostrar_progreso)
    except ErrorReconciliacion as error:
        print(f"\nERROR: {error.mensaje}", file=sys.stderr)
        if error.detalle:
            print(f"Detalle: {error.detalle}", file=sys.stderr)
        return 1

    _mostrar_resumen(resultado)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
