# Importador histórico CSV de Avisos y Demoras

ETL por lotes para 2025/2026, compatible con PostgreSQL del proyecto. Usa Python
3.12, `csv`/`zoneinfo` de la biblioteca estándar y psycopg 3.2.9 ya instalado en
la imagen backend. No requiere Node, pg, csv-parser ni nuevas dependencias.
No importa el módulo de arranque del servidor ni inicializa/migra su esquema.

## Entradas privadas

Desde la raíz del proyecto, colocar:

```text
data/legacy_import/avisos.csv
data/legacy_import/demoras.csv
data/legacy_import/mapping.json   # opcional
```

Se puede entregar solo uno de los CSV. `data/` está excluido de Git y del
empaquetador de servidor. No colocar archivos reales en `tools/` ni en ejemplos.
No se modifica ningún CSV. Exportar desde Excel como CSV UTF-8, conservando
teléfonos y números de tarea como texto para no perder ceros iniciales.

Admite BOM, separador `;`, `,` o tabulación, comillas y campos multilínea. Detecta
el separador; se recomienda `--delimiter ";"` cuando se conoce. Acepta la línea
Excel `sep=;`. Para Windows-1252 usar `--encoding cp1252`. Por defecto espera
encabezado con la primera columna Fecha; `--no-header` permite omitirlo.
El orden de columnas es obligatorio, independientemente del título del encabezado.

## Mapeo real de la aplicación

El esquema existente no tiene una tabla `delays` ni columnas `service_type`,
`zone_details`, `created_by`/`assigned_to` en estas entidades. No se cambió ese
contrato. La resolución parte de IDs reales de usuarios y guarda los nombres
actuales requeridos por la aplicación; los IDs quedan registrados en
`audit_events.after_data.user_ids` y el creador en `audit_events.actor_id`.

| CSV | Columna | Destino PostgreSQL |
| --- | --- | --- |
| Demoras | A Fecha y hora | `delay_zones.created_at` |
| Demoras | B Estado | `status`: VIGENTE / NORMALIZADO |
| Demoras | C Prestación | `service`: TODAS, GRÚA, ML, SINIESTROS |
| Demoras | D Departamento | `department`, catálogo canónico con tildes |
| Demoras | E Zona | `zone` |
| Demoras | F/G Tiempo | `message` y `minutes` |
| Demoras | H Agente | Usuario real → `agent` y auditoría con ID |
| Avisos | A Fecha y hora | `notices.created_at` y `updated_at` |
| Avisos | B/C Tarea y teléfono | `task_number` / `phone` como texto |
| Avisos | D Aviso | `notice_type` |
| Avisos | E Para | `audience`: TODOS / TELEFONISTAS / PLANIFICADORES |
| Avisos | F Detalle | `detail`, preservando saltos de línea |
| Avisos | G Creador | Usuario real → `communicated_by` y auditoría con ID |
| Avisos | H Responsable | Usuario real → `managed_by` y auditoría con ID |
| Avisos | I Estado | PENDIENTE / EN_GESTION / ESPERANDO_RESPUESTA / RESUELTO / CANCELADO |
| Avisos | J Comentarios | `comments` y evento de importación en `notice_events` |

Las fechas aceptan `DD/MM/YYYY HH:mm` (también segundos opcionales), se interpretan
en `America/Montevideo` y se guardan como instantes UTC. Los años se validan en
hora local antes de convertir. `--years 2025 2026` y `--timezone` permiten ajustar
explícitamente el alcance para otros conjuntos de datos.

No se inventa una fecha de cierre: `normalized_at` queda NULL cuando no está
en el CSV. `updated_at` de Avisos usa la fecha original porque el CSV no aporta
la última modificación. El evento/auditoría IMPORTADO usa la fecha de carga.
Las demoras mantienen el estado del origen, pero `expires_at=created_at` exige
revisión operativa antes de considerarlas vigentes verificadas. No se crean
eventos ficticios de verificación ni se reasignan registros ya existentes.

### Tiempo y prestaciones

- `Margen de;90`, `90 minutos`, `01:30`, `1,5 horas` y `1 h 30 min` equivalen a 90 min.
- Si F y G contienen ambos un valor, deben coincidir; no se suman automáticamente.
- `No confirmar tiempos` o `A confirmar` requieren la otra celda vacía o sin
  minutos. Los márgenes son enteros entre 1 y 1440. Rangos como `60 a 90`, valores
  contradictorios o formatos desconocidos se rechazan para corregir el CSV.
- `SIN` se convierte en SINIESTROS. `SIN Y ML` genera SINIESTROS y ML, ambos con
  los mismos datos históricos. No se convierte a TODAS porque incluiría GRÚA.
  Las dos inserciones se confirman juntas o se revierten juntas.

### Usuarios y equivalencias manuales

Se busca coincidencia exacta de username o display_name, ignorando mayúsculas,
tildes y espacios repetidos. No hay coincidencia difusa, creación automática de
usuarios ni asignación al administrador como fallback. Se admiten usuarios
inactivos existentes para preservar autoría histórica. Los responsables vacíos,
`-`, `Sin asignar` o `Sin responsable` quedan NULL; el creador siempre es obligatorio.

Si un alias es desconocido/ambiguo, la fila se registra como error. Obtener los
IDs mediante la administración autorizada de usuarios y completar un JSON privado:

```json
{
  "users": { "Valdes": 123, "Jeny G": 456 },
  "services": { "SIN Y ML": ["SINIESTROS", "ML"] },
  "audiences": { "Planificación": "PLANIFICADORES" }
}
```

123/456 son ejemplos: reemplazarlos por IDs reales. No hay contraseñas en el mapa.
Los aliases duplicados contradictorios o IDs inexistentes detienen la validación.
Si dos usuarios tienen el mismo display_name, la auditoría distingue sus IDs,
pero la interfaz conserva la limitación de nombres de su esquema actual.

## Ejecutar en Docker

La base debe estar inicializada y accesible. En el servidor conservar `.env`,
el nombre Compose y los volúmenes definidos por Sistemas. Antes de aplicar en
producción, disponer de un respaldo verificado y revisar los errores del simulador.
No se ejecutó ninguna carga sobre datos operativos al desarrollar esta herramienta.

Desde la raíz (PowerShell o shell Linux), simulación de solo lectura:

```sh
docker compose -f compose.yaml -f compose.production.yaml run --rm --no-deps -v "${PWD}/data/legacy_import:/imports:ro" -v "${PWD}/tools/legacy_import:/app/tools/legacy_import:ro" app python -B -m tools.legacy_import.import_csv --input-dir /imports --delimiter ";"
```

Aplicar después de revisar la simulación:

```sh
docker compose -f compose.yaml -f compose.production.yaml run --rm --no-deps -v "${PWD}/data/legacy_import:/imports:ro" -v "${PWD}/tools/legacy_import:/app/tools/legacy_import:ro" app python -B -m tools.legacy_import.import_csv --input-dir /imports --delimiter ";" --apply
```

Para desarrollo local configurado sin el override de producción, omitir solo
`-f compose.production.yaml`. El contenedor usa DATABASE_URL de Compose; no pasar
credenciales en comandos. El montaje del código permite ejecutar la herramienta
sin reconstruir la imagen. No expone un puerto adicional ni reinicia servicios.

## Transacciones, duplicados y resultados

- Simulación predeterminada: conexión de solo lectura, SELECT a usuarios y
  auditoría. Valida transformaciones, pero no prueba constraints/triggers de
  escritura. No reserva IDs ni crea tablas.
- Aplicación: lotes de 500 filas (`--batch-size`), INSERT parametrizados con
  eventos/auditoría. SAVEPOINT por fila; una fecha mala, alias no resuelto o
  constraint rechazado no impide cargar las siguientes. No es un COPY sin control.
- Una huella SHA-256 del tipo de CSV y sus celdas identifica cada fila en la
  auditoría. Ignora nombre de archivo, número de línea, separador y espacios en
  extremos; una reejecución omite filas ya importadas por ESTA herramienta.
  También agrupa filas exactamente idénticas dentro del CSV. No detecta duplicados
  previos creados manualmente o por otra herramienta. Cambiar el contenido de una
  fila origina otra huella: no usarlo para actualizar registros ya importados.
- Un bloqueo transaccional coordina ejecuciones concurrentes de este importador.
  No se crean tablas ni índices nuevos, ni se actualizan/eliminan registros existentes.
- Fallos de conexión/esquema detienen el proceso; los lotes confirmados permanecen.
  Una fila con error de integridad se revierte con todos sus eventos y puede
  reintentarse. Un CSV estructuralmente roto (comillas sin cierre/codificación)
  detiene ese archivo porque no siempre se puede recuperar la próxima fila;
  se continúa con el otro CSV.
- Consola: archivo, línea, categoría de error y recuentos; nunca teléfonos,
  detalles, nombres personales, DSN ni mensajes SQL con valores.
- `valid`: filas transformadas (incluye duplicados y rechazos posteriores de BD).
  `inserted_rows`: filas CSV confirmadas; `inserted_records`: registros de negocio
  (puede ser mayor por SIN Y ML); `duplicates` y `errors`: filas omitidas.
- Códigos de salida: 0 sin errores, 2 con filas/archivos rechazados, 1 fallo global.

## Pruebas reproducibles aisladas

`test_import.py` usa registros ficticios y DDL extraído del backend sin importar
su arranque. PostgreSQL 16 corre sin puertos, sin volumen persistente y en una red
interna exclusiva. Requiere las imágenes locales, no descargas. Desde PowerShell:

```powershell
$testCompose = @('--env-file','tools/legacy_import/test.env','-p','libro-legacy-import-tests','-f','tools/legacy_import/compose.test.yaml')
try {
  docker compose @testCompose up -d --wait --pull never db
  if ($LASTEXITCODE -ne 0) { throw 'No inició la base de pruebas' }
  docker compose @testCompose run --rm --no-deps --pull never tests
  if ($LASTEXITCODE -ne 0) { throw 'Fallaron las pruebas del importador' }
} finally {
  docker compose @testCompose down
}
```

Comprueba fechas y cambio de año UTC, minutos, alias ambiguos, expansión de
servicios, UTF-8 BOM, ceros iniciales, campos multilínea, dry run sin escrituras,
continuación tras error SQL, atomicidad de eventos y reintentos sin duplicados.
No ejecutar este test contra otra base: tiene una guarda de conexión explícita.
