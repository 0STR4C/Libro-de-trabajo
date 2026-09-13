# Arquitectura técnica

## Ejecución

Centro Operativo ofrece dos adaptadores HTTP. `app/local_server.py` usa SQLite
para el modo de escritorio local. `app/postgres_server.py` usa FastAPI y
PostgreSQL para la operación multiusuario en Docker. Ambos sirven la interfaz de
`app/static/` y deben conservar el mismo comportamiento funcional.

Los adaptadores dependen de módulos compartidos y no deben importarse entre sí:

- `application.py`: versión, permisos y roles iniciales;
- `identity.py`: correo corporativo, Google y coordenadas/rutas;
- `notices.py`: estados, permisos de actualización y duplicados;
- `quotes.py`: catálogo, límites y redondeos del cotizador;
- `dashboard.py`, `delays.py`, `transfers.py`, `scheduling.py`, `reporting.py`,
  `tolls.py` y `wfm.py`: reglas de los dominios operativos;
- `security.py`: secretos, contraseñas, CSRF y límites de autenticación;
- `migrations.py`: checksums y compatibilidad del registro de migraciones.

Las consultas y transacciones específicas permanecen en cada adaptador. Una
regla nueva debe entrar primero en un módulo compartido y recibir pruebas puras;
los servidores solo traducen HTTP, permisos y persistencia. La prueba
`tests/test_server_boundaries.py` impide que PostgreSQL vuelva a depender del
servidor SQLite.

## Persistencia

SQLite guarda `centro_operativo.db`. PostgreSQL guarda el estado operativo en el
volumen `postgres_data`; no publica el puerto de la base. Los scripts de prueba
usan el proyecto Compose `librodetrabajo-tests`, su propio volumen y una base
aleatoria por ejecución.

El esquema todavía conserva una fase de bootstrap idempotente dentro de ambos
adaptadores. `schema_migrations` registra las transformaciones incrementales. En
SQLite, los registros históricos reciben un checksum y un cambio posterior de
una definición aplicada detiene el arranque. Las nuevas transformaciones deben
tener una clave nueva; nunca se edita una migración aplicada.

## Seguridad y red

Desarrollo admite HTTP en loopback. Producción exige secretos fuertes y
`PUBLIC_BASE_URL=https://...`; FastAPI debe quedar en `127.0.0.1:8000` detrás de
un proxy TLS privado. Las cookies de sesión son `HttpOnly`, `Secure` y
`SameSite=Strict`. Consulte `SECURITY.md` y `DEPLOY_LOCAL_NETWORK.md`.

## Decisiones de compatibilidad

- El modo SQLite continúa disponible y no se usa en paralelo con PostgreSQL.
- Las migraciones son aditivas y las interfaces HTTP existentes se conservan.
- Los datos WFM locales son entradas operativas excluidas de Git; su contrato se
  documenta en `DATA_MANIFEST.md`.
- `CHANGELOG.md` es la fuente del historial visible y `APP_VERSION`, en
  `app/application.py`, identifica la entrega actual.
