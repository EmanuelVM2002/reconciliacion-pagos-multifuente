# Sistema de Reconciliación de Pagos Multi-Fuente

Cruce de transacciones de pago entre tres orígenes que describen la misma
operación desde ángulos distintos, para encontrar dónde dejan de coincidir.

| Fuente | Archivo | Qué representa | Cómo llama a la llave |
|---|---|---|---|
| CSV | `datos/autorizaciones.csv` | Lo que se **autorizó** | `ID_Transaccion` |
| SQLite | `datos/reconciliacion_pagos.db` | Lo que se **contabilizó** | `Referencia` |
| JSON | `datos/movimientos_bancarios.json` | Lo que **llegó al banco** | `transaccion_id` |

El resultado es un Excel de una sola hoja (`Reconciliacion`) con una fila por
transacción del universo —la unión de las tres fuentes— con los valores de cada
origen lado a lado, la clasificación del hallazgo y la marcación de fraude.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

**Interfaz gráfica** (doble clic en `ejecutar_gui.bat`, o):

```bash
python ejecutar_gui.py
```

**Terminal**:

```bash
python main.py
```

Ambas corren la cadena completa —carga, validación, limpieza, reconciliación,
detección de fraude y exportación— y dejan el Excel en
`salida/reporte_reconciliacion.xlsx`.

No hay selectores de archivo por ningún lado: todas las rutas viven en
`reconciliacion/config/rutas.py`.

**Pruebas**:

```bash
python -m pytest
```

## Estructura

```
reconciliacion-pagos-multifuente/
├── datos/                       # Las tres fuentes de entrada
├── reconciliacion/
│   ├── config/rutas.py          # Todas las rutas, en un solo lugar
│   ├── dominio/                 # Modelos, enumeraciones y la transacción reconciliada
│   ├── loaders/                 # Un cargador por fuente, con contrato común
│   ├── limpieza/                # Extracción de los campos malformados del CSV
│   ├── procesamiento/           # Reconciliación, reglas y detección de fraude
│   ├── exportadores/            # Generación del Excel
│   └── gui/                     # Interfaz Tkinter + customtkinter
├── tests/                       # Pruebas unitarias (pytest)
└── salida/                      # Donde queda el Excel generado
```

Separé el proyecto en capas para que cada pieza tenga una sola razón para
cambiar. Los *loaders* solo leen, la *limpieza* solo interpreta, el
*procesamiento* solo decide y los *exportadores* solo presentan. En la práctica
eso significa que puedo probar el parseo de un campo corrupto pasándole un
string, sin tocar disco, y que agregar una cuarta fuente mañana solo obliga a
escribir un cargador nuevo.

## Decisiones que tomé

### La llave de cruce

Las tres fuentes usan el mismo identificador `TRXxxxx` pero con distinto nombre
de campo. Esa traducción la resuelven los cargadores: de ahí para adentro todo
el sistema habla de `id_transaccion` y nadie más se entera de cómo se llamaba
en el archivo original.

### Limpieza del CSV: extraer, no reparar

El campo `Monto` del CSV no es un número y el campo `Marca` no es solo la
marca: ambos traen estructuras tipo JSON deliberadamente malformadas. Probé
primero a repararlas para poder usar `json.loads()` y lo descarté: hay al menos
seis variantes de corrupción conviviendo en el archivo (aperturas `[{`, `{{` o
`({`, cierres `}}]""` o `})"`, claves con escapes sobrantes como `"monto\":` y
claves duplicadas pegadas como `financial_entityfinancial_entity"`), así que
cualquier reparación genérica se rompe con alguna de ellas.

Opté por **extraer con expresiones regulares tolerantes** el dato que me
interesa, sin importar cómo venga escapado alrededor. Es más robusto y, sobre
todo, no pierde filas: de las 500 del archivo extraje monto, marca y
retenciones en las 500.

Tres detalles del archivo que obligan a decidir:

- **El monto viene en tres formatos**: `1250000`, `"188.000 COP"` y
  `"$175.000,00"`. El tercero es formato colombiano (punto = miles, coma =
  decimales); si se interpreta el punto como decimal, `$175.000,00` se
  convierte en 17.500.000 y aparecen 53 discrepancias de monto que no existen.
- **La clave `monto` puede estar repetida** en la misma fila con valores
  distintos. Apliqué la semántica estándar de JSON: gana la última. En el único
  caso del archivo (TRX0138: `"410.000 COP"` y `1720000`) el valor que gana es
  el que confirman SQLite y el banco.
- **Una misma entidad de retención puede repetirse** en la fila con montos
  distintos: pasa en 267 de las 500 filas. Hay que sumar todas sus ocurrencias
  antes de aplicar las fórmulas; quien parsee a un diccionario simple pierde
  valores sin darse cuenta.

Ninguna fila se descarta. Si algo no se puede extraer, la transacción se
conserva con ese campo vacío y queda registrada una incidencia en el log: en un
proceso contable prefiero una fila visible e incompleta que una fila ausente.

### Normalización de la marca

Las tres fuentes no escriben la marca igual. El CSV guarda el nombre comercial
completo y SQLite y el banco guardan solo su primera palabra:

| CSV | SQLite / JSON |
|---|---|
| `NAF NAF` | `NAF` |
| `AMERICAN EAGLE` | `AMERICAN` |
| `AMERICANINO` | `AMERICANINO` |
| `CHEVIGNON` | `CHEVIGNON` |
| `RIFLE` | `RIFLE` |

Mi regla de normalización es: **mayúsculas, sin tildes ni puntuación, espacios
colapsados y me quedo solo con el primer token**. Comparando literalmente me
daban 183 marcas "distintas" sobre 500 que en realidad son la misma; tras
normalizar, cero.

Elegí el primer token y no un recorte por prefijo común porque es una regla
estable y explicable, y porque el catálogo no tiene dos marcas que compartan la
primera palabra: `AMERICANINO` y `AMERICAN EAGLE` normalizan a `AMERICANINO` y
`AMERICAN`, que siguen siendo distintas. No introduce colisiones.

### Clasificación

Cada criterio de negocio es una clase con una sola responsabilidad
(`ReglaPresencia`, `ReglaMonto`, `ReglaEstado`, `ReglaFechas`,
`ReglaReconciliado`) y todas comparten la misma interfaz. El motor solo las
recorre en orden sin saber qué hace cada una, así que cambiar un criterio no
obliga a tocar el motor.

Dos decisiones ahí:

- **Los estados no se comparan como texto.** Cada fuente tiene su propio
  vocabulario (`AUTORIZADO`, `CONTABILIZADO`, `COMPLETADO`) y los tres son el
  mismo estado "OK". Solo marco `DISCREPANCIA_ESTADO` cuando SQLite dice
  `PENDIENTE` o `RECHAZADO`.
- **La regla de presencia cubre las siete combinaciones posibles**, no solo las
  tres que nombra el enunciado. Así ninguna transacción del universo se queda
  sin clasificar, aunque aparezca una combinación que hoy no existe en los
  datos.

El desfase de fechas (tolerancia ±2 h) lo dejo como observación y no como
etiqueta: el enunciado pide comprobarlo pero no define una etiqueta para él, y
preferí no inventar vocabulario nuevo. En estos datos ninguna transacción se
sale de la tolerancia.

### Detección de fraude

El fraude lo traté como una **dimensión aparte** de la clasificación, no como
una etiqueta más: una transacción puede estar perfectamente reconciliada y aun
así ser fraude. De hecho pasa en 90 de las 505.

La diferencia técnica con las reglas de clasificación es que aquí el contrato
recibe **toda la colección** y no una transacción suelta, porque tres de los
cuatro patrones lo necesitan: el umbral de monto anómalo se calcula sobre la
distribución completa y el patrón sospechoso compara unas transacciones contra
otras.

Dos criterios que tuve que fijar porque el enunciado no los cierra:

- **Desviación estándar poblacional, no muestral.** El conjunto analizado no es
  una muestra de algo mayor: es la población completa de transacciones del
  periodo. Sobre estos datos ambas dan el mismo resultado (11 transacciones),
  así que no cambia la salida, pero prefiero que el criterio sea explícito.
- **Fecha de referencia = la primera disponible en el orden CSV → SQLite →
  JSON.** La autorización es el momento en que la operación realmente ocurre;
  la contabilización y el movimiento bancario son ecos posteriores de ese
  hecho. Es la fecha que uso para la hora inusual y para el patrón.

En el patrón sospechoso marco **todas** las transacciones involucradas, no solo
la segunda de cada par, y en la observación dejo escrito con cuáles cruza.

### El reporte de Excel

Las 29 columnas están declaradas como **datos** (una lista de `ColumnaReporte`
con su título, cómo obtener el valor y con qué formato mostrarse), no como 29
bloques de código repetido. El método que escribe la hoja es el mismo sin
importar cuántas columnas haya, y mover o agregar una es editar una línea.

Los montos y las fechas se escriben como número y como `datetime` reales, con
formato de Excel aplicado — no como texto —, para que el área contable pueda
filtrar, sumar y ordenar sin tener que convertir nada.

El color de fila sigue la precedencia pedida: naranja si hay fraude, si no rojo
para cualquier hallazgo, si no verde. Usé los tonos convencionales de Excel
para "malo" y "bueno" porque son los que un área contable ya reconoce sin
necesidad de leyenda.

Un caso que vale la pena mirar en el archivo es **TRX0001**: está
`RECONCILIADO` (verde por clasificación) pero es `FRAUDE_MONTO`, así que la
fila sale naranja. Es la precedencia funcionando y la prueba visual de que
clasificación y fraude son dimensiones distintas.

### Por qué diseñé así la interfaz

Pensé la ventana para una persona de contabilidad que no programa y que no va a
abrir una terminal. Necesita responder tres cosas de un vistazo —*¿funcionó?*,
*¿qué tan sano está el resultado?*, *¿dónde está mi archivo?*— y, mientras
espera, saber que el proceso sigue vivo.

La organicé en cuatro bloques que siguen ese orden mental:

1. **Fuentes de datos.** Antes de ejecutar nada ya dice si los tres archivos
   están donde deben, con un punto verde o rojo. Es el error más probable en la
   vida real y no tiene sentido descubrirlo a mitad del proceso: si falta algo,
   el botón queda deshabilitado y el mensaje dice qué falta y dónde debería
   estar, con el nombre del archivo y no con una ruta técnica.
2. **Acción y avance.** Un solo botón. La barra va acompañada del paso escrito
   en palabras ("Escribiendo el reporte... (320/505)"), porque una barra sola no
   dice si el proceso avanza o si se atascó.
3. **Cuatro indicadores.** Porcentaje reconciliado, transacciones analizadas,
   monto en discrepancia y transacciones con fraude. Son cuatro y no veinte: si
   todo es importante, nada lo es. Van aquí y no en el Excel, como pide el
   enunciado.
4. **Detalle del proceso.** La bitácora completa para quien quiera auditar qué
   se hizo, y los botones para abrir el Excel o su carpeta.

**Lo que dejé fuera a propósito:** selectores de archivo (las rutas son
configuración, no una decisión del usuario), una tabla con las 505
transacciones (para eso está el Excel, que filtra y ordena mucho mejor) y
gráficos (decoran, no ayudan a decidir). Sí agregué selector de tema claro y
oscuro, que cuesta tres líneas y se agradece.

Antes de ejecutar nada, la ventana no está vacía ni muestra ceros: muestra el
estado de las fuentes y dice explícitamente que todavía no se ha generado
ningún reporte.

### Que la interfaz no se congele: lo que costó de verdad

El requisito técnico central era que la ventana nunca se congelara. Puse el
proceso en un hilo aparte que se comunica con la interfaz por una `queue.Queue`
—Tkinter no es seguro para hilos, así que el trabajo pesado no toca ni un
widget— y la ventana la vacía cada 60 ms con `after()`.

**Eso no fue suficiente, y medirlo fue la parte interesante.** Instrumenté la
aplicación para contar cuántas veces alcanzaba a ejecutarse el hilo de la
interfaz durante el proceso, y el resultado fue malo: 4 ejecuciones en 1,7
segundos, con un hueco de **1,57 s sin repintar**. La barra saltaba de 0 % a
100 % de golpe. El culpable no era el diseño sino el GIL: el hilo de trabajo
usa 100 % de CPU y el intérprete solo lo interrumpe cada 5 ms por defecto, lo
que en la práctica dejaba al hilo de la ventana sin turnos.

Lo resolví con tres cambios, y volví a medir cada uno:

- **Avance de grano fino.** Las etapas largas (limpieza, clasificación,
  escritura del Excel) avisan cada 20 elementos, no solo al terminar. El
  servicio traduce ese conteo al porcentaje global, así que la barra avanza de
  forma continua.
- **Ceder el turno al avisar.** Una pausa real de 1 ms en cada aviso.
  `sleep(0)` no sirve en Windows: solo cede a hilos que ya estén listos, y el
  de la interfaz suele estar esperando un evento.
- **Bajar el intervalo de conmutación del intérprete** a 0,5 ms mientras dura
  el proceso, y restaurarlo al terminar.

Resultado medido: el hueco máximo sin repintar bajó de **1,57 s a 0,15 s** y la
barra pasó de mostrar 2 estados a mostrar 9. Ahí sí se cumple el requisito.

También encontré, probándolo, que cerrar la ventana con el proceso corriendo
dejaba callbacks de `after` programados sobre una ventana muerta y Tcl escribía
errores en consola. Se cancelan al cerrar.

**Los errores se manejan dentro de la ventana**, nunca en consola. Probé los
tres casos: falta un archivo (botón deshabilitado y mensaje explicando qué
falta), error previsible como el Excel abierto en otra ventana (mensaje en
lenguaje del usuario y detalle técnico en la bitácora) y error inesperado
(mensaje genérico, detalle en la bitácora). En los tres la ventana sigue viva y
el botón vuelve a habilitarse.

### Las pruebas

158 pruebas con pytest, repartidas donde de verdad se puede romper algo:

| Archivo | Qué cubre |
|---|---|
| `test_montos.py` | Los tres formatos de monto y la clave `monto` duplicada |
| `test_marcas.py` | Extracción y la regla del primer token |
| `test_retenciones.py` | Emparejamiento, entidades repetidas, signos y las tres sumas |
| `test_reglas.py` | Las reglas de clasificación y las siete combinaciones de presencia |
| `test_fraude.py` | Los cuatro patrones, los bordes (05:59 sí, 06:00 no; 60 min sí, 61 no) y la prioridad de riesgo |
| `test_transaccion.py` | Monto y fecha de referencia, diferencias, presencia |
| `test_loaders.py` | Carga de las tres fuentes y los errores: archivo ausente, JSON inválido, tabla inexistente, ids duplicados |
| `test_excel.py` | Estructura, formatos y color por precedencia |
| `test_servicio.py` | La cadena completa sobre los datos reales |

Dos decisiones sobre cómo las escribí:

- **Los casos de los parsers salen del archivo real.** No inventé cadenas
  malformadas: usé las variantes de corrupción que efectivamente aparecen en
  `autorizaciones.csv`, incluido el caso concreto de TRX0138.
- **`test_servicio.py` fija los números.** Corre el proceso completo y afirma
  505 transacciones, 290 reconciliadas, 149 fraudes y el conteo exacto por
  etiqueta. Si alguien toca un parser, una regla o el umbral de fraude y los
  totales se mueven, esa prueba lo dice en el acto. Es la red de seguridad que
  me permite refactorizar sin miedo.

Para los errores que en producción no se pueden provocar (un archivo que
desaparece, un JSON roto) escribo archivos temporales en la prueba, en vez de
tocar los datos reales.

## Resultado sobre los datos entregados

| Indicador | Valor |
|---|---|
| Universo (unión de las 3 fuentes) | 505 |
| Reconciliadas | 290 (57,4 %) |
| Discrepancia de monto | 95 |
| Discrepancia de estado | 55 |
| No encontradas en el banco | 40 |
| No contabilizadas | 20 |
| No autorizadas (solo en el banco) | 5 |
| Monto total | $124.690.000 |
| Monto en discrepancia | $475.000 |

Fraude (dimensión transversal, umbral de monto anómalo en $733.774):

| Patrón | Transacciones |
|---|---|
| Hora inusual (00:00–05:59) | 134 |
| Patrón sospechoso | 12 |
| Monto anómalo (> media + 3σ) | 11 |
| Sin autorización | 5 |
| **Total con al menos un patrón** | **149** |

Por nivel de riesgo: 5 críticas, 6 altas y 138 medias. Las cinco transacciones
que el banco reporta sin autorización previa son además de monto anómalo y de
madrugada, así que las tres señales apuntan al mismo sitio.

## Estado

- [x] Configuración de rutas centralizada
- [x] Carga y validación de integridad de las tres fuentes
- [x] Limpieza y extracción de los campos malformados del CSV
- [x] Reconciliación y clasificación
- [x] Detección de fraude
- [x] Script ejecutable de punta a punta (`main.py`)
- [x] Reporte Excel
- [x] Interfaz gráfica (+ `.bat` para abrirla con doble clic)
- [x] Pruebas unitarias (158, todas pasando)
