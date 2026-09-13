# Prueba aislada de restauración PostgreSQL

Valida un dump de PostgreSQL sin tocar el volumen operativo. Comprueba el
checksum, restaura con `--no-owner` en PostgreSQL 16, revisa tablas, filas,
restricciones, referencias WFM y secuencias, y ejecuta la inicialización de la
aplicación actual.

## Requisitos

- Docker Desktop activo.
- La imagen `librodetrabajo-app:latest` construida localmente.
- Un dump `.dump` y su archivo lateral `.dump.sha256`.

No instala paquetes, no publica puertos y usa un `tmpfs` descartable.

## Uso

Desde la raíz del proyecto:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\postgres_restore_test\run.ps1
powershell -ExecutionPolicy Bypass -File .\tools\postgres_restore_test\run.ps1 -DumpPath .\postgres-backups\ARCHIVO.dump
```

La salida `Status = OK` indica que la restauración y la inicialización fueron
correctas. El script detiene y elimina únicamente el contenedor temporal.
Nunca se debe cambiar el destino para apuntar al volumen PostgreSQL operativo.

Entradas: dump y checksum. Salida: informe de validación en pantalla. No
modifica archivos del proyecto, la base SQLite histórica ni la base activa.
