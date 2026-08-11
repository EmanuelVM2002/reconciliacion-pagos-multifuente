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

```bash
python main.py
```

Corre la cadena completa —carga, validación, limpieza, reconciliación,
detección de fraude y exportación— mostrando el avance y un resumen al final.
El Excel queda en `salida/reporte_reconciliacion.xlsx`.

No hay selectores de archivo por ningún lado: todas las rutas viven en
`reconciliacion/config/rutas.py`.

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
- [ ] Interfaz gráfica
- [ ] Pruebas unitarias
