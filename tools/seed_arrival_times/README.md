# Datos de prueba de Tiempos de arribo

`seed_arrival_times.py` genera 40 tiempos base sintéticos entre 30 y 75 minutos.
Usa los 19 departamentos y solo zonas del catálogo de `app/geography.py`.
Incluye registros activos e inactivos para probar el filtro de estado. Cada fila
tiene una clave `seed_key`, por lo que repetir el script no duplica los datos.

La pantalla **Tiempos de arribo** consulta `GET /api/arrival-times` con
`items`, `total`, `limit` (máximo 50) y `offset`. También hay filtro por
departamento, servicio y estado, catálogo en `/api/arrival-times/geography`,
detalle por ID y alta, edición y desactivación bajo la misma ruta. Las lecturas
requieren `standards.view`; los cambios requieren el permiso dinámico
`arrival_times.manage`. Las referencias heredadas de `arrival_standards` y sus
endpoints permanecen independientes.

El runtime es la imagen Docker de la aplicación. Desde la raíz del proyecto:

```powershell
docker compose up -d --build app
docker compose exec -T app python -m tools.seed_arrival_times.seed_arrival_times
docker compose exec -T app python -m tools.seed_arrival_times.seed_arrival_times --apply
```

`--apply` inserta solo filas nuevas en `arrival_times`; el script no borra ni
reemplaza registros existentes. Las filas llevan `created_by` y `updated_by`
igual a `Seed de pruebas`. La salida informa el plan y cuántas filas insertó.

Para validar el backend en PostgreSQL aislado:

```powershell
docker build -f tools/seed_delays/Dockerfile.pytest -t librodetrabajo-delays-pytest:local .
& .\tools\postgres_test_db\run.ps1 -ImageName librodetrabajo-delays-pytest:local -TestCommand @('python','-m','pytest','tests/test_arrival_times_pytest.py','-q','-p','no:cacheprovider')
```
