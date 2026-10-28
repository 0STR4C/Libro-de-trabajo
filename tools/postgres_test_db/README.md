# PostgreSQL aislado para pruebas

La base manual `test_operativa` se mantiene mediante `start.ps1`. Cada ejecución
de `run.ps1` crea otro proyecto Compose con identificador aleatorio, su propia
red y su propio volumen; ejecuta las pruebas y elimina únicamente ese proyecto.
No comparte recursos ni credenciales con la base operativa.

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

Puede validar una imagen candidata sin cambiar etiquetas globales:

```powershell
& .\tools\postgres_test_db\run.ps1 -ImageName librodetrabajo-app:1.30.0
```

Para ejecutar otra suite con la misma base aislada, pasar el comando del
contenedor en `-TestCommand`. Por ejemplo, la suite Pytest de demoras:

```powershell
& .\tools\postgres_test_db\run.ps1 -ImageName librodetrabajo-delays-pytest:local -TestCommand @('python','-m','pytest','tests/test_delay_api_pytest.py','-q')
```

El comando inicia un PostgreSQL efímero con puerto de loopback asignado por
Docker, ejecuta las pruebas y elimina su propio volumen al terminar. Dos
ejecuciones pueden convivir. La base manual `test_operativa` y su volumen no se
tocan. Si la prueba falla y también falla la limpieza, se conserva el primer
error y se informa el segundo.

## Detener sin perder datos

```powershell
& .\tools\postgres_test_db\stop.ps1
```

## Entradas y salidas

La entrada de la suite es el código actual del proyecto, montado como solo lectura
en el contenedor. La salida indica la cantidad vigente de pruebas PostgreSQL y
su resultado en la consola.

Los recursos efímeros pertenecen a un proyecto `librodetrabajo-suite-...`.
El proyecto manual `librodetrabajo-tests` y su volumen permanecen intactos.
Ningún script modifica archivos ni datos de la aplicación operativa.

El archivo `AGENTS.md` de la raíz obliga a usar este flujo al finalizar futuras
mejoras del proyecto.
