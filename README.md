# LineFlow — Módulo Interactivo de Secuenciación y Cronometraje en Línea de Ensamblaje

Sistema (interfaz y código en inglés, documentación en español) para ingenieros de
métodos y tiempos. Permite **secuenciar, rebalancear y cronometrar** los elementos de
trabajo de una línea de ensamble en tiempo real. Toda la lógica de secuencias está
escrita en **Python** y se basa en **listas doblemente enlazadas con manejo explícito
de punteros** (`prev`, `next`, `head`, `tail`, `cursor`).

![Vista general](docs/img/vista_general.png)

## Características

| Necesidad del analista | Cómo lo resuelve LineFlow | Estructura / costo |
|---|---|---|
| Reordenar pasos para equilibrar cargas | *Drag and drop* entre estaciones, atajos `Alt + flechas` | Reenlace de nodo **O(1)** |
| Insertar o eliminar elementos intermedios | Botón `+` entre tarjetas, tecla `N`, botón eliminar | Enlace/desenlace **O(1)** |
| Mover una estación completa | Flechas ◀ ▶ en la cabecera de la estación | Empalme de segmento **O(1)** |
| Navegar el cronómetro de vueltas | Flechas `←` `→`, botones ⏮ ◀ ▶ ⏭ | Cursor por `prev`/`next` **O(1)** |
| Corregir errores de marcaje | Corregir lectura, eliminar marca, insertar marca olvidada | **O(1)** por punteros |
| Ver el balanceo al instante | Diagrama Yamazumi + indicadores (eficiencia, retraso, etc.) | Cargas mantenidas en **O(1)**, métricas O(S) |
| Probar escenarios | Deshacer/rehacer, fijar escenario base y comparar | Historial como lista doble |
| Calcular tiempo estándar | Media observada × valoración × (1 + suplementos) | Recorrido de vueltas O(L) |

## Requisitos

* **Python 3.9 o superior.** 

## Ejecución

```bash
cd lineflow
python run.py
```

Se abre automáticamente `http://127.0.0.1:8000`. Opciones:

```bash
python run.py --port 9000       # otro puerto
python run.py --no-browser      # no abrir el navegador
python run.py --host 0.0.0.0    # permitir acceso desde otra PC/tablet de la red
python run.py --verbose         # registrar cada petición HTTP
```

## Estructura del proyecto

```
lineflow/
├── run.py                          # Punto de entrada (servidor + navegador)
├── services/
│   ├── core/
│   │   └── doubly_linked_list.py   # Nodo, lista doble, cursor, punteros, validación
│   ├── domain/
│   │   ├── models.py               # WorkElement, Station, catálogo de Therbligs
│   │   ├── assembly_line.py        # Línea: lista única del proceso + segmentos por estación
│   │   ├── stopwatch.py            # Cronómetro de vueltas (split times) con cursor
│   │   ├── balancing.py            # Indicadores de balanceo de línea
│   │   ├── history.py              # Deshacer / rehacer (lista doble)
│   │   └── seed.py                 # Datos de demostración (ensamble de ventilador)
│   ├── service.py                  # Servicio de aplicación + instrumentación de punteros
│   └── web/
│       ├── server.py               # Servidor HTTP (biblioteca estándar)
│       ├── api.py                  # Rutas REST/JSON
│       └── static/                 # index.html, styles.css, app.js (front-end)
├── benchmarks/                     # Comparación de rendimiento
└── docs/                           # Mock-Up
```
