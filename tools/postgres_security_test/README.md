# Prueba aislada de seguridad PostgreSQL

Ejecuta `tests/test_postgres_security.py` contra una PostgreSQL 16 efímera y separada de la operación. No conecta con `librodetrabajo_postgres_data`, no publica puertos y monta únicamente `tests/` como solo lectura. La base temporal usa `tmpfs`; el contenedor se detiene y elimina al finalizar, incluso si una prueba falla.

## Requisitos

- Docker Desktop iniciado.
- Imagen local `librodetrabajo-app:latest`, generada con `docker compose build app` o al abrir el lanzador de escritorio.
- PowerShell 7 o Windows PowerShell 5.1.

## Uso

Desde la raíz del proyecto:

```powershell
.\tools\postgres_security_test\run.ps1
```

Si Docker no está en `PATH`:

```powershell
.\tools\postgres_security_test\run.ps1 -DockerPath "C:\ruta\a\docker.exe"
```

## Entradas, salidas y modificaciones

- Entrada: la imagen local de la aplicación y `tests/test_postgres_security.py`.
- Salida: resultado detallado de las pruebas en la consola.
- Modificaciones: crea solamente un contenedor temporal llamado `centro-operativo-security-test-*`; no crea volúmenes persistentes ni modifica archivos del proyecto, respaldos o bases activas.
# Imagen candidata

El parámetro opcional `-ImageName centro-wfm-candidate:latest` permite probar una
imagen local alternativa sin cambiar la imagen que utiliza la aplicación activa.
