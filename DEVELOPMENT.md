# Desarrollo y validación

## Requisitos

- Docker Desktop con Compose v2.
- PowerShell 5.1 o posterior.
- Node.js para validar JavaScript.
- Imágenes locales `librodetrabajo-app:latest` y `postgres:16-alpine`.

No se requieren credenciales operativas ni acceso a Internet para las pruebas.

## Flujo de cambio

1. Revisar `git status` y preservar cambios existentes.
2. Crear la regla en el módulo de dominio compartido.
3. Mantener en cada servidor únicamente la consulta o traducción propia de su
   base de datos.
4. Agregar una prueba del comportamiento y, si aplica, una prueba de paridad.
5. Ejecutar desde la raíz:

   ```powershell
   & .\tools\test_all\run.ps1
   ```

Ese comando ejecuta la suite general, valida JavaScript, ejecuta la prueba UI si
Playwright está disponible y siempre llama a
`tools/postgres_test_db/run.ps1`. La base PostgreSQL operativa no participa.

## Migraciones

Los cambios de esquema deben ser compatibles con una base existente, tener una
clave única y ser idempotentes. No cambie el contenido asociado a una clave ya
registrada: el checksum existe para detectar esa situación. Valide tres casos:

1. base vacía;
2. base con la versión anterior;
3. segunda inicialización sin cambios.

No use `docker compose down -v` y no restaure pruebas sobre el volumen
operativo. El procedimiento obligatorio está en
`tools/postgres_test_db/README.md`.

## Entrega

Actualice `CHANGELOG.md`, `app/application.py`, README y la nota de continuidad.
Construya una imagen con etiqueta de versión, ejecute la validación completa y
revise `git diff --check`. Producción usa `--no-build` con la imagen ya validada.
