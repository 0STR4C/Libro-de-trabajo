# Lanzador de escritorio de Centro Operativo

## Libro de Trabajo: ejecutable con identidad propia

El nuevo ejecutable es `tools/desktop_launcher/dist-libro/LibroDeTrabajo.exe`.
Incluye el icono multirresolución de `app/static/libro-trabajo.ico` en el archivo
y en su ventana. La salida anterior `dist/CentroOperativo.exe` se conserva.
No mover el EXE solo: conservar sus archivos vecinos y mantener la carpeta
dentro del proyecto (o crear un acceso directo desde Windows).

Compilación sin restaurar ni descargar dependencias:

```powershell
dotnet publish tools/desktop_launcher/CentroOperativoLauncher.csproj -c Release --no-restore -p:AssemblyName=LibroDeTrabajo -o tools/desktop_launcher/dist-libro
```

Si es necesario, establecer `DOTNET_CLI_HOME` en `.build/dotnet` del proyecto
para no escribir en el perfil personal durante la compilación. No se instala
software ni se modifican variables globales.

Este proyecto genera `CentroOperativo.exe`, un lanzador gráfico para Windows. El ejecutable no contiene una copia de los datos ni reemplaza la aplicación web: encuentra la carpeta del proyecto, comprueba Docker Desktop, ejecuta `docker compose up -d app`, espera `/health` y abre el navegador.

## Requisitos

- Windows x64.
- Docker Desktop instalado y autorizado para ejecutarse.
- El ejecutable debe permanecer dentro de la carpeta del proyecto o en una subcarpeta para poder localizar `compose.yaml`.
- Para el ejecutable publicado actualmente se requiere .NET 8 Desktop Runtime. El código no descarga ni instala componentes.

## Compilar

Desde la raíz del proyecto:

```powershell
dotnet publish .\tools\desktop_launcher\CentroOperativoLauncher.csproj -c Release -r win-x64 --self-contained false -o .\tools\desktop_launcher\dist
```

Salida:

```text
tools\desktop_launcher\dist\CentroOperativo.exe
```

## Uso

Hacer doble clic en `CentroOperativo.exe`. El botón **Iniciar / actualizar** ejecuta:

```powershell
docker compose up -d --build app
```

El botón **Detener servicios** usa `docker compose stop app backup db`; conserva el volumen PostgreSQL. El lanzador nunca ejecuta el perfil `migration` y nunca usa `docker compose down -v`.

## Entradas, salidas y datos

- Entrada: `compose.yaml`, `.env` si existe y la instalación local de Docker Desktop.
- Salida: servicios Docker activos y navegador en `http://127.0.0.1:8000/`.
- No modifica `centro_operativo.db`, `postgres_data` ni `postgres-backups/` directamente.
- El lanzador no muestra ni guarda credenciales; los mensajes de proceso ocultan valores con nombres `PASSWORD`, `SECRET` o `TOKEN`.

## Comprobación mínima

```powershell
dotnet build .\tools\desktop_launcher\CentroOperativoLauncher.csproj -c Release
```

No copiar el `.exe` a otra computadora sin copiar también el proyecto Docker o ajustar la ubicación para que el ejecutable encuentre `compose.yaml`.
