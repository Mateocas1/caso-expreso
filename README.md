# Caso Expreso · LogiSur → Expreso Andino

Puente en Python entre el export diario de remitos de LogiSur y la API de envíos de Expreso Andino. Toma el export, se queda con los remitos que viajan por Expreso Andino, los transforma al formato de la API, los carga y deja un resumen de la corrida para operaciones. Se puede volver a correr sin duplicar envíos.

Solo usa la librería estándar (Python 3.9+): no hay nada que instalar.

## Cómo correrlo

```bash
# 1. Levantar la API de prueba (en otra terminal)
python3 kit/expreso_api.py

# 2. Configurar la API key (la URL es opcional, por defecto http://localhost:8000)
export EXPRESO_API_KEY=andino-test-7f3a91
# export EXPRESO_API_URL=http://localhost:8000

# 3. Cargar los envíos del export
python3 -m expreso_bridge upload kit/remitos_2026-09-30.json
# -> deja el resumen en reports/corrida_<fecha-hora>.md

# Opcional: envíos atrasados a una fecha
python3 -m expreso_bridge overdue kit/remitos_2026-09-30.json --today 2026-10-03
# -> lo imprime por pantalla; para guardarlo: > reports/atrasados_2026-10-03.md
```

Códigos de salida de `upload`, pensados para una corrida programada:

| Código | Significado |
| --- | --- |
| `0` | Todo cargado o ya existente. Nada que hacer. |
| `1` | La corrida terminó, pero hay remitos rechazados o fallidos: alguien tiene que mirar el resumen. |
| `2` | No se pudo correr: no se puede leer el export, falta la API key, la key es inválida o la API no responde al arrancar. |

Tests (incluyen una corrida de punta a punta contra la API de prueba, que levantan solos):

```bash
python3 -m unittest
```

## Resultado con los datos del kit

Resúmenes generados contra la API de prueba en [`reports/`](reports/):

- [Primera corrida](reports/corrida_2026-10-29T161817_763102.md): 51 remitos en el export, 24 de Expreso Andino → 19 cargados, 1 ya existía, 1 duplicado en el export, 3 rechazados.
- [Segunda corrida](reports/corrida_2026-10-29T161818_832683.md), sobre la misma API: 0 cargados, 20 ya existían. No duplica nada.
- [Atrasados al 2026-10-03](reports/atrasados_2026-10-03.md).

## Cómo está armado

```
expreso_bridge/
  remitos.py    lectura del export, filtro por transportista y mapeo remito → envío (sin red)
  client.py     cliente HTTP de la API con reintentos
  upload.py     carga cada remito y clasifica el resultado
  report.py     resumen en Markdown para operaciones
  overdue.py    envíos atrasados (opcional)
  __main__.py   línea de comandos
tests/          tests unitarios y de punta a punta
kit/            lo que vino con el challenge, sin modificar: export, API de prueba y su documentación
reports/        resúmenes generados contra la API de prueba
```

La transformación es lógica pura y está separada de la red: se testea sin levantar nada y es donde están casi todas las reglas del negocio.

Cada remito termina en exactamente uno de estos resultados:

| Resultado | Cuándo | Qué hacer |
| --- | --- | --- |
| Cargado | La API lo creó (`201`) | Nada |
| Ya existía | La API ya lo tenía (`409`) | Nada |
| Duplicado en el export | El mismo `nro_remito` aparece más de una vez en el archivo | Nada, se procesa la primera aparición |
| Rechazado | El dato no se puede mapear o la API lo rechaza (`422`) | Corregir en el sistema de LogiSur y volver a correr |
| Falló | La API siguió con error (`5xx` o sin conexión) después de reintentar | Volver a correr |

## Datos del export y cómo se tratan

| Lo que viene | Cómo se resuelve |
| --- | --- |
| Transportista escrito de muchas formas (`EXPRESO ANDINO`, `Expreso Andino`, `EXPRESO ANDINO ` con espacio, `expreso andino`, `Exp. Andino`) | Se compara normalizado (sin mayúsculas, acentos ni espacios de más) contra los nombres conocidos |
| Provincias que no coinciden con las de la API (`BA`, `Bs. As.`, `Cba`, `CABA`, `Capital Federal`, `Tucuman`, `Neuquen`) | Se toma la lista oficial de `GET /v1/provinces` y se compara normalizado; las abreviaturas van en una tabla de alias. Si no se reconoce, se rechaza sin llamar a la API |
| Peso como número o como texto con coma decimal (`"145,1"`) | Se convierte a número. Si no se puede leer sin ambigüedad, se rechaza |
| Servicio `NORMAL` / `URGENTE` | `standard` / `express` |
| Remito repetido en el export (`R-10000507`) | Se carga una sola vez y la repetición queda informada |
| Bultos en `0`, dirección en blanco, código postal vacío | Se envían tal cual (con los espacios recortados) y la API los rechaza con `422`. El resumen muestra el campo con el nombre que tiene en el export y las observaciones del remito |
| Campos que la API no usa (`volumen_m3`, `cliente`, `fecha_remito`) | No se envían |

Las reglas de negocio (bultos ≥ 1, campos obligatorios, etc.) no se duplican: el que valida es la API, que es la fuente de verdad. Del lado nuestro solo se rechaza lo que no se puede traducir.

## Errores de la API e idempotencia

- **`409` ya existe**: `external_ref` (el número de remito) es único en la API. Por eso volver a correr no duplica: lo que ya está vuelve como "Ya existía" con su tracking.
- **`500` / `503` o sin conexión**: hasta 4 intentos (3 reintentos) con espera exponencial (0,5 s, 1 s, 2 s). Reintentar un POST es seguro por la misma unicidad de `external_ref`.
- **Error y después `409`**: si un intento devuelve `5xx` pero la API igual guardó el envío, el reintento recibe `409`. Ese caso se informa como "Cargado" (casi seguro lo creó esta corrida), no como "Ya existía". Pasa en la corrida de prueba. El caso borde: si el envío ya existía de antes y además el primer intento dio `5xx`, también se vería como "Cargado"; el tracking es el correcto igual.
- **`401`**: corta toda la corrida. Es un problema de configuración, no de un remito.
- **`422`**: el remito queda rechazado con el detalle de la API.

No hace falta guardar estado local para ser idempotente: la API ya garantiza la unicidad.

## Supuestos

- `BA` y `Bs. As.` son la provincia de Buenos Aires (las localidades del export lo confirman: Pilar, Mar del Plata). `CABA` y `Capital Federal` son la Ciudad Autónoma de Buenos Aires.
- `Exp. Andino` es Expreso Andino.
- Si un remito aparece repetido, se toma la primera aparición. En el export los dos registros son idénticos.
- Un peso con separador de miles (`1.234,5`) o no numérico (`nan`, `inf`) se rechaza en vez de adivinarlo. Un texto con punto (`"1.234"`) se lee como decimal (1,234 kg). Ninguno de estos casos aparece en los datos.
- Un envío está atrasado si no está `DELIVERED` y su fecha estimada es anterior a la fecha de referencia. Uno que vence ese mismo día todavía no cuenta como atrasado. `EXCEPTION` cuenta como no entregado.
- Para los atrasados se consultan los remitos de Expreso Andino del export indicado.
- Los textos para operaciones (resumen, ayuda del CLI) están en castellano; el código, en inglés.

## Para usarlo en producción todos los días

- **Programarlo** (cron o un scheduler) con alerta cuando el código de salida no es `0`, y mandar el resumen al canal de operaciones en lugar de dejarlo en una carpeta.
- **Secretos** en un gestor (Vault, AWS Secrets Manager, etc.), no en variables exportadas a mano.
- **Volumen**: hoy las cargas van una por una. Con miles de remitos por día, primero conviene paralelizar con un pool chico de workers (`concurrent.futures`), respetando el rate limit del expreso, y reusar conexiones HTTP (keep-alive, por ejemplo `requests.Session`). El diseño ya lo permite: cada remito se procesa de forma independiente y la idempotencia la garantiza la API. Si el export pasara a pesar cientos de MB, se puede leer en streaming.
- **Atrasados**: hoy son 2 llamadas por envío (buscar por referencia y pedir el estado). En producción guardaría el `tracking_id` de cada carga (una tabla chica o una base) para no buscarlo, y le pediría al expreso un endpoint de consulta en lote o webhooks de estado.
- **API caída a mitad de corrida**: hoy cada remito pendiente agota sus reintentos (si está caída desde el inicio, la corrida corta enseguida). Cortaría la corrida después de varios fallos seguidos (circuit breaker) para no esperar de más.
- **Calidad del dato en origen**: los rechazos se repiten todos los días hasta que se corrige el sistema de LogiSur. Pasaría las abreviaturas de provincias y el formato del peso como pedido de mejora al equipo dueño del export.
- **Observabilidad**: logs estructurados (JSON) y métricas de cargados, rechazados y fallidos por corrida.
- **Resumen en CSV** además del Markdown, si operaciones lo quiere filtrar en una planilla.
