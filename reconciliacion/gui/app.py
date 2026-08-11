"""La ventana.

Pense esto para alguien de contabilidad que no programa y que no va a abrir una
terminal. Necesita responder tres cosas de un vistazo —funciono?, que tan sano
esta el resultado?, donde esta mi archivo?— y, mientras espera, saber que el
proceso sigue vivo.

De ahi salen los cuatro bloques, en el orden en que uno los mira:

1. las tres fuentes, con un punto verde o rojo, antes de ejecutar nada;
2. el boton y la barra, con el paso escrito en palabras;
3. cuatro indicadores, no veinte;
4. el detalle del proceso y el acceso al archivo.

Lo que deje fuera a proposito: selectores de archivo, una tabla con las 505
transacciones (para eso esta el Excel, que filtra mejor que cualquier cosa que yo
dibuje) y graficos, que decoran pero no ayudan a decidir.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import customtkinter as ctk

from reconciliacion.config import rutas
from reconciliacion.gui.mensajes import Mensaje, TipoMensaje
from reconciliacion.gui.trabajador import TrabajadorReconciliacion
from reconciliacion.servicio import ResultadoProceso

#: Cada cuantos milisegundos la interfaz revisa la cola del hilo de trabajo.
INTERVALO_SONDEO_MS = 60

#: Cuantos mensajes se atienden como maximo en cada revision. Ver `_procesar_cola`.
MAXIMO_MENSAJES_POR_CICLO = 250

#: Tamano ideal de la ventana; se recorta si el monitor es mas pequeno.
ANCHO_PREFERIDO = 1000
ALTO_PREFERIDO = 760

#: Tamano minimo por debajo del cual la ventana deja de ser usable.
ANCHO_MINIMO = 880
ALTO_MINIMO = 600

# Todos los colores van como pares (tema claro, tema oscuro). Un mismo tono no
# sirve para los dos fondos: el verde y el naranja que se leen bien sobre
# negro pierden contraste sobre blanco, asi que la version clara es mas oscura.
COLOR_OK = ("#1E7A4F", "#2FA572")
COLOR_ERROR = ("#B02F2A", "#D9534F")
COLOR_AVISO = ("#A06510", "#E8A33D")
COLOR_NEUTRO = ("#5C5C5C", "#9A9A9A")

SIN_DATO = "—"

#: Un color de customtkinter: un tono unico o el par (tema claro, tema oscuro).
Color = Union[str, Tuple[str, str]]

# Los colores se declaran como pares (tema claro, tema oscuro): customtkinter
# elige el que corresponda. Fijarlos a un solo valor es lo que hace que un
# boton legible en oscuro desaparezca en claro.
BORDE_SECUNDARIO = ("#B4B4B4", "#4A4A4A")
TEXTO_SECUNDARIO = ("#2B2B2B", "#DCE4EE")
TEXTO_SECUNDARIO_INACTIVO = ("#8E8E8E", "#6E6E6E")
FONDO_SECUNDARIO_ENCIMA = ("#E6E6E6", "#3A3A3A")


def estilo_boton_secundario() -> Dict[str, object]:
    """Devuelve el estilo comun de los botones que no son la accion principal.

    Existe para no repetir seis argumentos en cada boton y, sobre todo, para
    que el color deshabilitado quede definido en un solo lugar: con el valor
    por defecto de customtkinter, un boton inactivo es casi invisible sobre
    fondo claro.

    Returns:
        Los argumentos de estilo listos para pasarle a `CTkButton`.
    """
    return {
        "fg_color": "transparent",
        "border_width": 1,
        "border_color": BORDE_SECUNDARIO,
        "text_color": TEXTO_SECUNDARIO,
        "text_color_disabled": TEXTO_SECUNDARIO_INACTIVO,
        "hover_color": FONDO_SECUNDARIO_ENCIMA,
    }


class TarjetaIndicador(ctk.CTkFrame):
    """Tarjeta que muestra un indicador agregado con su titulo."""

    def __init__(self, maestro: ctk.CTkBaseClass, titulo: str, color: Color) -> None:
        """Crea la tarjeta.

        Args:
            maestro: Contenedor padre.
            titulo: Nombre del indicador.
            color: Color del valor —un par (claro, oscuro)— para distinguir
                buenas y malas noticias.
        """
        super().__init__(maestro, corner_radius=8)
        self.valor = ctk.CTkLabel(
            self,
            text=SIN_DATO,
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=color,
        )
        self.valor.pack(padx=16, pady=(14, 2))
        ctk.CTkLabel(
            self, text=titulo, font=ctk.CTkFont(size=11), text_color=COLOR_NEUTRO
        ).pack(padx=16, pady=(0, 14))

    def actualizar(self, texto: str) -> None:
        """Cambia el valor mostrado.

        Args:
            texto: Nuevo valor ya formateado.
        """
        self.valor.configure(text=texto)


class AplicacionReconciliacion(ctk.CTk):
    """Ventana principal: lanza el proceso y muestra su resultado."""

    def __init__(self) -> None:
        """Construye la ventana y deja la interfaz en su estado inicial."""
        super().__init__()

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.title("Reconciliacion de Pagos Multi-Fuente")
        self._ajustar_al_monitor()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self.cola: "queue.Queue[Mensaje]" = queue.Queue()
        self.trabajador: Optional[TrabajadorReconciliacion] = None
        self.ruta_reporte: Optional[Path] = None
        self.indicadores: Dict[str, TarjetaIndicador] = {}

        self._construir_encabezado()
        self._construir_fuentes()
        self._construir_acciones()
        self._construir_indicadores()
        self._construir_bitacora()

        self._revisar_fuentes()
        self._sondeo: Optional[str] = self.after(INTERVALO_SONDEO_MS, self._procesar_cola)
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    def _ajustar_al_monitor(self) -> None:
        """Dimensiona y centra la ventana segun el monitor disponible.

        No se fija un tamano absoluto: en una pantalla de 1366x768 —muy comun
        en equipos de oficina— una ventana de 760 px mas la barra de titulo se
        sale por abajo y el mensaje que dice donde quedo el reporte queda
        fuera de la pantalla, invisible justo para quien mas lo necesita.
        """
        margen_horizontal, margen_vertical = 80, 90
        ancho = min(ANCHO_PREFERIDO, self.winfo_screenwidth() - margen_horizontal)
        alto = min(ALTO_PREFERIDO, self.winfo_screenheight() - margen_vertical)

        posicion_x = max(0, (self.winfo_screenwidth() - ancho) // 2)
        posicion_y = max(0, (self.winfo_screenheight() - alto) // 3)

        self.geometry(f"{ancho}x{alto}+{posicion_x}+{posicion_y}")
        self.minsize(min(ANCHO_MINIMO, ancho), min(ALTO_MINIMO, alto))

    # --- Construccion de la ventana ---------------------------------------

    def _construir_encabezado(self) -> None:
        """Titulo, subtitulo y selector de tema."""
        marco = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        marco.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 4))
        marco.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            marco,
            text="Reconciliacion de Pagos",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            marco,
            text="Cruce de autorizaciones (CSV), contabilizaciones (SQLite) y movimientos bancarios (JSON)",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_NEUTRO,
        ).grid(row=1, column=0, sticky="w")

        selector = ctk.CTkSegmentedButton(
            marco, values=["Claro", "Oscuro"], command=self._cambiar_tema, width=150
        )
        selector.set("Oscuro" if ctk.get_appearance_mode() == "Dark" else "Claro")
        selector.grid(row=0, column=1, rowspan=2, sticky="e")

        # Va arriba y en tono discreto: es una salida, no la accion principal,
        # y no debe competir visualmente con el boton de ejecutar.
        ctk.CTkButton(
            marco,
            text="Salir",
            command=self._salir,
            width=80,
            **estilo_boton_secundario(),
        ).grid(row=0, column=2, rowspan=2, sticky="e", padx=(10, 0))

    def _construir_fuentes(self) -> None:
        """Panel con el estado de los tres archivos de entrada."""
        marco = ctk.CTkFrame(self, corner_radius=8)
        marco.grid(row=1, column=0, sticky="ew", padx=20, pady=8)
        marco.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            marco, text="FUENTES DE DATOS", font=ctk.CTkFont(size=11, weight="bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(12, 6))

        self.etiquetas_fuente: Dict[str, ctk.CTkLabel] = {}
        for fila, (nombre, ruta) in enumerate(rutas.FUENTES_REQUERIDAS.items(), start=1):
            punto = ctk.CTkLabel(marco, text="●", font=ctk.CTkFont(size=16), width=20)
            punto.grid(row=fila, column=0, sticky="w", padx=(16, 4))
            ctk.CTkLabel(marco, text=nombre, font=ctk.CTkFont(size=12)).grid(
                row=fila, column=1, sticky="w"
            )
            ctk.CTkLabel(
                marco,
                text=ruta.name,
                font=ctk.CTkFont(size=11),
                text_color=COLOR_NEUTRO,
            ).grid(row=fila, column=2, sticky="e", padx=16)
            self.etiquetas_fuente[nombre] = punto

        ctk.CTkLabel(marco, text="").grid(row=4, column=0, pady=2)

    def _construir_acciones(self) -> None:
        """Boton de ejecucion, barra de progreso y paso actual."""
        marco = ctk.CTkFrame(self, corner_radius=8)
        marco.grid(row=2, column=0, sticky="ew", padx=20, pady=8)
        marco.grid_columnconfigure(2, weight=1)

        self.boton_ejecutar = ctk.CTkButton(
            marco,
            text="Ejecutar reconciliacion",
            command=self._ejecutar,
            height=42,
            width=210,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.boton_ejecutar.grid(row=0, column=0, rowspan=2, padx=(16, 8), pady=16)

        self.boton_cancelar = ctk.CTkButton(
            marco,
            text="Cancelar",
            command=self._cancelar,
            height=42,
            width=100,
            state="disabled",
            **estilo_boton_secundario(),
        )
        self.boton_cancelar.grid(row=0, column=1, rowspan=2, padx=(0, 16), pady=16)

        self.barra = ctk.CTkProgressBar(marco, height=14)
        self.barra.set(0)
        self.barra.grid(row=0, column=2, sticky="ew", padx=(0, 16), pady=(20, 4))

        self.etiqueta_paso = ctk.CTkLabel(
            marco,
            text="Listo para ejecutar. Aun no se ha generado ningun reporte.",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_NEUTRO,
            anchor="w",
        )
        self.etiqueta_paso.grid(row=1, column=2, sticky="ew", padx=(0, 16), pady=(0, 16))

    def _construir_indicadores(self) -> None:
        """Las cuatro cifras que resumen la salud del resultado."""
        marco = ctk.CTkFrame(self, fg_color="transparent")
        marco.grid(row=3, column=0, sticky="ew", padx=20, pady=4)

        definicion = (
            ("reconciliacion", "% reconciliado", COLOR_OK),
            ("transacciones", "Transacciones analizadas", None),
            ("discrepancia", "Monto en discrepancia", COLOR_AVISO),
            ("fraudes", "Transacciones con fraude", COLOR_ERROR),
        )
        for columna, (clave, titulo, color) in enumerate(definicion):
            marco.grid_columnconfigure(columna, weight=1)
            tarjeta = TarjetaIndicador(
                marco, titulo, color or ctk.ThemeManager.theme["CTkLabel"]["text_color"]
            )
            tarjeta.grid(row=0, column=columna, sticky="ew", padx=(0 if columna == 0 else 8, 0))
            self.indicadores[clave] = tarjeta

    def _construir_bitacora(self) -> None:
        """Bitacora del proceso y acceso al reporte generado."""
        marco = ctk.CTkFrame(self, corner_radius=8)
        marco.grid(row=4, column=0, sticky="nsew", padx=20, pady=(12, 8))
        marco.grid_columnconfigure(0, weight=1)
        marco.grid_rowconfigure(1, weight=1)

        cabecera = ctk.CTkFrame(marco, fg_color="transparent")
        cabecera.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        cabecera.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            cabecera, text="DETALLE DEL PROCESO", font=ctk.CTkFont(size=11, weight="bold")
        ).grid(row=0, column=0, sticky="w")

        self.boton_abrir = ctk.CTkButton(
            cabecera,
            text="Abrir reporte",
            command=self._abrir_reporte,
            width=130,
            state="disabled",
        )
        self.boton_abrir.grid(row=0, column=1, sticky="e", padx=(8, 0))

        self.boton_carpeta = ctk.CTkButton(
            cabecera,
            text="Abrir carpeta",
            command=self._abrir_carpeta,
            width=130,
            state="disabled",
            **estilo_boton_secundario(),
        )
        self.boton_carpeta.grid(row=0, column=2, sticky="e", padx=(8, 0))

        self.boton_bitacora = ctk.CTkButton(
            cabecera,
            text="Guardar bitacora",
            command=self._guardar_bitacora,
            width=140,
            state="disabled",
            **estilo_boton_secundario(),
        )
        self.boton_bitacora.grid(row=0, column=3, sticky="e", padx=(8, 0))

        self.bitacora = ctk.CTkTextbox(marco, font=ctk.CTkFont(family="Consolas", size=11))
        self.bitacora.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        self.bitacora.configure(state="disabled")

        self.etiqueta_estado = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=12),
            anchor="w",
            justify="left",
            wraplength=ANCHO_PREFERIDO - 60,
        )
        self.etiqueta_estado.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 14))

    # --- Comportamiento ---------------------------------------------------

    def _cambiar_tema(self, valor: str) -> None:
        """Alterna entre tema claro y oscuro.

        Args:
            valor: Opcion elegida en el selector.
        """
        ctk.set_appearance_mode("dark" if valor == "Oscuro" else "light")

    def _revisar_fuentes(self) -> bool:
        """Comprueba que los tres archivos existan y lo refleja en pantalla.

        Returns:
            `True` si estan las tres fuentes.
        """
        faltantes = rutas.fuentes_faltantes()
        for nombre, punto in self.etiquetas_fuente.items():
            punto.configure(text_color=COLOR_ERROR if nombre in faltantes else COLOR_OK)

        if faltantes:
            self._mostrar_estado(
                "No se encontraron: " + ", ".join(faltantes)
                + f". Deben estar en la carpeta {rutas.DIRECTORIO_DATOS.name}.",
                COLOR_ERROR,
            )
            self.boton_ejecutar.configure(state="disabled")
            return False

        self.boton_ejecutar.configure(state="normal")
        return True

    def _ejecutar(self) -> None:
        """Lanza la reconciliacion en segundo plano."""
        if not self._revisar_fuentes():
            return

        self.boton_ejecutar.configure(state="disabled", text="Procesando...")
        self.boton_cancelar.configure(state="normal")
        self.boton_abrir.configure(state="disabled")
        self.boton_carpeta.configure(state="disabled")
        self.boton_bitacora.configure(state="disabled")
        self.barra.set(0)
        self._limpiar_bitacora()
        self._mostrar_estado("", COLOR_NEUTRO)

        self.trabajador = TrabajadorReconciliacion(self.cola)
        self.trabajador.start()

    def _cancelar(self) -> None:
        """Pide al hilo de trabajo que se detenga de forma ordenada."""
        if self.trabajador is not None and self.trabajador.is_alive():
            self.trabajador.cancelar()
            self.boton_cancelar.configure(state="disabled", text="Cancelando...")
            self.etiqueta_paso.configure(text="Cancelando, espera un momento...")

    def _procesar_cola(self) -> None:
        """Consume la cola del hilo de trabajo y actualiza la ventana.

        Es el unico punto donde se tocan los widgets a partir de datos
        producidos por otro hilo, y corre siempre en el hilo de la interfaz.
        Se reprograma solo, de modo que la ventana sigue respondiendo aunque el
        proceso tarde.

        Atiende como maximo `MAXIMO_MENSAJES_POR_CICLO` mensajes por vuelta y
        no vacia la cola de un tiron: si el hilo de trabajo publica cientos de
        lineas de golpe, aplicarlas todas en un solo ciclo dejaria la ventana
        sin repintar y se perderia justamente la sensacion de avance. Lo que
        quede espera al siguiente ciclo, que llega en una decima de segundo.
        """
        lineas: List[str] = []
        try:
            for _ in range(MAXIMO_MENSAJES_POR_CICLO):
                mensaje = self.cola.get_nowait()
                if mensaje.tipo is TipoMensaje.LOG:
                    # Las lineas de bitacora se acumulan y se escriben de una
                    # sola vez: insertarlas una por una obliga a Tk a recalcular
                    # el textbox en cada linea y es lo que mas cuesta del ciclo.
                    lineas.append(mensaje.texto)
                else:
                    self._atender(mensaje)
        except queue.Empty:
            pass
        finally:
            if lineas:
                self._escribir("\n".join(lineas))
            if self.winfo_exists():
                self._sondeo = self.after(INTERVALO_SONDEO_MS, self._procesar_cola)

    def _salir(self) -> None:
        """Cierra la aplicacion desde el boton Salir.

        Hace exactamente lo mismo que cerrar la ventana con la X, para que las
        dos formas de salir se comporten igual y no haya una "buena" y una
        "mala".
        """
        self._al_cerrar()

    def _al_cerrar(self) -> None:
        """Cierra la ventana dejando todo en orden.

        Dos cuidados antes de destruir la ventana:

        * se le pide al hilo de trabajo que se detenga, para que no siga
          gastando la maquina ni escribiendo archivos despues de que el usuario
          ya se fue;
        * se cancela el sondeo pendiente, porque si no el `after` programado se
          dispara sobre una ventana que ya no existe y Tcl escribe un error en
          la consola.

        El hilo es `daemon`, asi que en ningun caso impide que el programa
        termine.
        """
        if self.trabajador is not None and self.trabajador.is_alive():
            self.trabajador.cancelar()

        if self._sondeo is not None:
            self.after_cancel(self._sondeo)
            self._sondeo = None

        self.destroy()

    def _atender(self, mensaje: Mensaje) -> None:
        """Aplica un mensaje del hilo de trabajo a la interfaz.

        Args:
            mensaje: Aviso recibido por la cola.
        """
        if mensaje.tipo is TipoMensaje.PROGRESO:
            self.barra.set(mensaje.porcentaje / 100)
            self.etiqueta_paso.configure(text=mensaje.texto)

        elif mensaje.tipo is TipoMensaje.LOG:
            self._escribir(mensaje.texto)

        elif mensaje.tipo is TipoMensaje.ERROR:
            self._terminar()
            self.barra.set(0)
            self.etiqueta_paso.configure(text="El proceso no pudo completarse.")
            self._mostrar_estado(mensaje.texto, COLOR_ERROR)
            self._escribir(f"ERROR: {mensaje.texto}")
            if mensaje.detalle:
                self._escribir(f"       {mensaje.detalle}")

        elif mensaje.tipo is TipoMensaje.CANCELADO:
            self._terminar()
            self.barra.set(0)
            self.etiqueta_paso.configure(text="Proceso cancelado.")
            self._mostrar_estado(mensaje.texto, COLOR_AVISO)
            self._escribir(mensaje.texto)

        elif mensaje.tipo is TipoMensaje.FIN and mensaje.resultado is not None:
            self._terminar()
            self.barra.set(1)
            self._mostrar_resultado(mensaje.resultado)

    def _mostrar_resultado(self, resultado: ResultadoProceso) -> None:
        """Vuelca los indicadores agregados y habilita el acceso al reporte.

        Args:
            resultado: Resultado devuelto por el servicio.
        """
        resumen = resultado.resumen
        fraude = resultado.resumen_fraude

        self.indicadores["reconciliacion"].actualizar(
            f"{resumen.porcentaje_reconciliacion:.1f}%"
        )
        self.indicadores["transacciones"].actualizar(f"{resumen.total:,}".replace(",", "."))
        self.indicadores["discrepancia"].actualizar(
            "$" + f"{resumen.monto_en_discrepancia:,.0f}".replace(",", ".")
        )
        self.indicadores["fraudes"].actualizar(str(fraude.total_fraudes))

        self.ruta_reporte = resultado.ruta_reporte
        if self.ruta_reporte is not None:
            self.boton_abrir.configure(state="normal")
            self.boton_carpeta.configure(state="normal")

        detalle = ", ".join(
            f"{etiqueta.replace('_', ' ').lower()}: {veces}"
            for etiqueta, veces in sorted(
                resumen.por_clasificacion.items(), key=lambda x: -x[1]
            )
        )
        self.etiqueta_paso.configure(
            text=f"Terminado en {resultado.duracion_segundos:.1f} s. "
            f"{resumen.reconciliadas} de {resumen.total} transacciones sin hallazgos."
        )
        self._mostrar_estado(
            f"Reporte generado en {self.ruta_reporte}. Detalle: {detalle}.", COLOR_OK
        )

    def _terminar(self) -> None:
        """Devuelve los botones a su estado de reposo.

        Se llama tanto al terminar bien como al fallar o al cancelar: pase lo
        que pase, la interfaz vuelve a quedar utilizable.
        """
        self.boton_ejecutar.configure(state="normal", text="Ejecutar reconciliacion")
        self.boton_cancelar.configure(state="disabled", text="Cancelar")
        if self.bitacora.get("1.0", "end").strip():
            self.boton_bitacora.configure(state="normal")

    def _guardar_bitacora(self) -> None:
        """Guarda el detalle del proceso en un archivo de texto.

        No abre un selector de archivos, por coherencia con el resto de la
        aplicacion: la bitacora va a la carpeta de salida con la fecha y la
        hora en el nombre, y se le dice al usuario donde quedo.
        """
        contenido = self.bitacora.get("1.0", "end").strip()
        if not contenido:
            self._mostrar_estado("No hay nada que guardar todavia.", COLOR_AVISO)
            return

        destino = rutas.asegurar_directorio_salida() / (
            f"bitacora_{datetime.now():%Y%m%d_%H%M%S}.txt"
        )
        try:
            destino.write_text(contenido, encoding="utf-8")
        except OSError as error:
            self._mostrar_estado(f"No se pudo guardar la bitacora: {error}", COLOR_ERROR)
            return

        self._mostrar_estado(f"Bitacora guardada en {destino}", COLOR_OK)

    def _abrir_reporte(self) -> None:
        """Abre el Excel generado con la aplicacion predeterminada."""
        self._abrir(self.ruta_reporte)

    def _abrir_carpeta(self) -> None:
        """Abre la carpeta donde quedo el reporte."""
        self._abrir(self.ruta_reporte.parent if self.ruta_reporte else None)

    def _abrir(self, destino: Optional[Path]) -> None:
        """Abre un archivo o carpeta con el explorador del sistema.

        Args:
            destino: Ruta a abrir. Si no existe se avisa en pantalla.
        """
        if destino is None or not destino.exists():
            self._mostrar_estado("El archivo ya no esta disponible.", COLOR_ERROR)
            return

        try:
            if sys.platform == "win32":
                os.startfile(destino)  # noqa: S606 - ruta propia, no entrada del usuario
            elif sys.platform == "darwin":
                subprocess.run(["open", str(destino)], check=False)
            else:
                subprocess.run(["xdg-open", str(destino)], check=False)
        except OSError as error:
            self._mostrar_estado(f"No se pudo abrir el archivo: {error}", COLOR_ERROR)

    # --- Utilidades de presentacion ---------------------------------------

    def _escribir(self, texto: str) -> None:
        """Agrega una linea a la bitacora y baja el scroll.

        Args:
            texto: Linea a mostrar.
        """
        self.bitacora.configure(state="normal")
        self.bitacora.insert("end", texto + "\n")
        self.bitacora.see("end")
        self.bitacora.configure(state="disabled")

    def _limpiar_bitacora(self) -> None:
        """Vacia la bitacora antes de una nueva ejecucion."""
        self.bitacora.configure(state="normal")
        self.bitacora.delete("1.0", "end")
        self.bitacora.configure(state="disabled")

    def _mostrar_estado(self, texto: str, color: Color) -> None:
        """Muestra el mensaje de estado al pie de la ventana.

        Args:
            texto: Mensaje a mostrar.
            color: Par (claro, oscuro) del texto, segun la gravedad.
        """
        self.etiqueta_estado.configure(text=texto, text_color=color)


def lanzar() -> None:
    """Abre la ventana principal."""
    AplicacionReconciliacion().mainloop()
