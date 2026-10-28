# Datos sintéticos de Zonas con demora

`seed_delays.py` prepara **72 demoras** para revisar paginación, filtros y estados:
36 vigentes, 20 vigentes con revisión vencida y 16 normalizadas. Recorre los
19 departamentos y solo usa zonas del catálogo de `app/geography.py`.

## Ejecución

El runtime es Docker. Desde la raíz del proyecto, después de reconstruir la
imagen, ver el plan sin escribir:

```powershell
docker compose exec -T app python -m tools.seed_delays.seed_delays
```

Insertar en la PostgreSQL **local** de Docker Compose:

```powershell
docker compose exec -T app python -m tools.seed_delays.seed_delays --apply
```

Para SQLite, la ruta debe estar dentro del proyecto y ser accesible desde el
contenedor. Ejemplo en un contenedor con el proyecto montado en `/work`:

```powershell
docker run --rm --network none -v "${PWD}:/work" -w /work librodetrabajo-app:latest python -m tools.seed_delays.seed_delays --backend sqlite --sqlite-path /work/tests/delays_visual.sqlite --apply
```

No se requieren paquetes adicionales. El script utiliza `DATABASE_URL` ya
configurada en el contenedor para PostgreSQL; no la imprime. `--apply` es
obligatorio para insertar. Una segunda ejecución salta los registros ya
marcados, sin reemplazarlos ni borrarlos.

## Datos escritos

Escribe en `delay_zones`, `delay_events` y, cuando haga falta, en
`operational_zones`. Los registros se reconocen por el valor `agent` que empieza
con `Prueba demoras [seed-v1:`. El script no modifica otras demoras ni elimina
datos. Las 20 revisiones vencidas continuarán vencidas mañana; las 36 vigentes
quedan con revisión futura para facilitar la comprobación visual.

La salida informa el plan y cuántas filas nuevas insertó. En la aplicación,
buscar `Prueba demoras` permite encontrar las filas sintéticas. Los datos también
afectan los contadores y alertas del Resumen local. La retirada de estos datos
debe tratarse como una tarea separada y explícita.

## Verificación

Las pruebas de backend se ejecutan sobre una base PostgreSQL aislada por
ejecución mediante `tools/postgres_test_db/run.ps1`; no reutilizan la base de la
aplicación. La imagen de pruebas instala Pytest solo en esa imagen, sin agregarlo
a las dependencias de producción:

```powershell
docker build -f tools/seed_delays/Dockerfile.pytest -t librodetrabajo-delays-pytest:local .
.\tools\postgres_test_db\run.ps1 -ImageName librodetrabajo-delays-pytest:local -TestCommand @('python','-m','pytest','tests/test_delay_api_pytest.py','-q')
```

El ejecutor crea una base nueva, ejecuta las pruebas y luego detiene el
contenedor de PostgreSQL de pruebas. Comprueba contrato HTTP, duración,
catálogo, índices y la idempotencia de los 72 registros sintéticos.
