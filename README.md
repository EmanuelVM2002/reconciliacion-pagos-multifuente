# Sistema de Reconciliación de Pagos Multi-Fuente

Reconciliación de transacciones de pago cruzando tres orígenes que describen la
misma operación desde ángulos distintos:

| Fuente | Archivo | Qué representa | Llave |
|---|---|---|---|
| CSV | `datos/autorizaciones.csv` | Lo que se **autorizó** | `ID_Transaccion` |
| SQLite | `datos/reconciliacion_pagos.db` | Lo que se **contabilizó** | `Referencia` |
| JSON | `datos/movimientos_bancarios.json` | Lo que **llegó al banco** | `transaccion_id` |

El resultado es un Excel de una sola hoja (`Reconciliacion`) con una fila por
transacción del universo (la unión de las tres fuentes), sus valores lado a
lado, la clasificación del hallazgo y la marcación de fraude.

> 🚧 Proyecto en construcción — se está desarrollando por fases.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

Pendiente (fases siguientes).

## Estructura

```
reconciliacion-pagos/
├── datos/                    # Fuentes de entrada
├── reconciliacion/
│   ├── config/rutas.py       # Configuración centralizada de rutas
│   ├── dominio/              # Modelos del dominio
│   ├── loaders/              # Carga de cada fuente
│   ├── limpieza/             # Parseo de los campos malformados del CSV
│   ├── procesamiento/        # Reconciliación y detección de fraude
│   ├── exportadores/         # Generación del Excel
│   └── gui/                  # Interfaz Tkinter + customtkinter
├── tests/                    # Pruebas unitarias (pytest)
└── salida/                   # Excel generado
```
