# PostgreSQL aislado para pruebas

Mantiene una instancia PostgreSQL exclusiva para desarrollo y ejecuta
`tests.test_postgres_security` contra una base interna nueva en cada corrida. No
comparte red, volumen ni credenciales con la base operativa.

La instancia conserva `test_operativa` para reproducir casos manualmente. Está
publicada solamente en `127.0.0.1:54329`, por lo que no acepta conexiones desde
otras computadoras.

## Requisitos

- Docker Desktop con Docker Compose.
- La imagen local `librodetrabajo-app:latest`, generada con `docker compose build app`.
- PowerShell 7 o Windows PowerShell 5.1.

No requiere instalar paquetes adicionales ni acceder a Internet si las imágenes
`postgres:16-alpine` y `librodetrabajo-app:latest` ya están disponibles localmente.

## Iniciar o reutilizar la base

```powershell
& .\tools\postgres_test_db\start.ps1
```

Datos de conexión para herramientas locales:

```text
Host: 127.0.0.1
Puerto: 54329
Base: test_operativa
Usuario: test_runner
Contraseña: test_only_password
```

Estas credenciales son exclusivas del entorno local de pruebas.

## Ejecutar la suite PostgreSQL

Desde la raíz del proyecto:

```powershell
& .\tools\postgres_test_db\run.ps1
```

El comando inicia el servidor, crea una base con nombre aleatorio, ejecuta las
pruebas, elimina solo esa base y detiene el servidor incluso si la suite falla.
`test_operativa` y el volumen permanecen disponibles para la próxima ejecución.

## Detener sin perder datos

```powershell
& .\tools\postgres_test_db\stop.ps1
```

## Entradas y salidas

La entrada de la suite es el código actual del proyecto, montado como solo lectura
en el contenedor. La salida es el resultado de las 26 pruebas en la consola.

Los recursos pertenecen al proyecto Docker `librodetrabajo-tests`. El volumen
`librodetrabajo-tests_test_postgres_data` conserva los datos de `test_operativa`.
Ningún script modifica archivos ni datos de la aplicación operativa.

El archivo `AGENTS.md` de la raíz obliga a usar este flujo al finalizar futuras
mejoras del proyecto.
