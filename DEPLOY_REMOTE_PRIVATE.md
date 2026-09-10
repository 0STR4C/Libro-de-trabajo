# Acceso remoto privado mediante Tailscale

Este procedimiento prepara el acceso, pero no instala ni configura Tailscale automáticamente.

## Diseño

```text
usuario autorizado → Tailscale HTTPS/Serve → 127.0.0.1:8000 → app → red interna Docker → PostgreSQL
```

No usar Tailscale Funnel. No abrir el puerto 8000 en el router. No publicar PostgreSQL.

## Preparación Docker

1. Crear `.env` siguiendo [SECURITY.md](SECURITY.md). No usar los marcadores de `.env.example`.
2. Definir `ALLOWED_HOSTS` con `localhost`, `127.0.0.1` y el nombre DNS exacto que Tailscale vaya a utilizar.
3. Definir `ALLOWED_ORIGINS` con el origen HTTPS exacto, sin comodines.
4. Mantener `HTTPS_CONFIRMED=false` hasta completar la comprobación HTTPS.
5. Iniciar o reanudar:

   ```powershell
   docker compose up -d app
   docker compose ps
   ```

   La salida debe mostrar `127.0.0.1:8000->8000/tcp` para `app`, y ningún puerto publicado para `db`.

## Configuración posterior de Tailscale

Instalar Tailscale y autorizarlo es una acción separada que requiere aprobación del administrador. Antes de ejecutarla, comprobar la sintaxis disponible en esa versión:

```powershell
tailscale serve --help
```

Configurar únicamente un destino HTTPS privado hacia `http://127.0.0.1:8000`, usando el comando de Serve indicado por la versión instalada. No ejecutar `tailscale funnel` ni habilitar una ruta pública.

Después de configurar Serve:

1. Confirmar desde un dispositivo autorizado que el navegador llega por HTTPS.
2. Revisar el nombre de host y el origen exactos que aparecen en la solicitud.
3. Ajustar `ALLOWED_HOSTS`, `ALLOWED_ORIGINS` y, solo si corresponde, `TRUSTED_PROXY_IPS` al proxy local real.
4. Reiniciar únicamente `app` y verificar `/health`.
5. Establecer `HTTPS_CONFIRMED=true` solo cuando el acceso HTTPS haya sido comprobado.

No confiar en `X-Forwarded-For` por defecto. Solo agregar a `TRUSTED_PROXY_IPS` la dirección local exacta del proxy que se haya verificado en los logs, nunca una red amplia o un comodín.

## Comprobación de exposición

Desde el servidor:

```powershell
docker compose ps
Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -InformationLevel Quiet
```

El primer comando debe mostrar el enlace `127.0.0.1:8000`. Para demostrar que no queda accesible directamente desde la LAN, obtener la IPv4 física del servidor y ejecutar desde otro equipo de la misma red:

```powershell
Test-NetConnection -ComputerName <IP_LAN_DEL_SERVIDOR> -Port 8000 -InformationLevel Quiet
```

El resultado esperado es `False`. Si resulta `True`, detener el procedimiento y no habilitar Tailscale Serve hasta corregir la exposición. Esta comprobación no requiere abrir puertos ni modificar el Firewall.

## Detención y reversión

```powershell
docker compose down
```

No usar `docker compose down -v`: eliminaría el volumen PostgreSQL. Para revertir la preparación, restaurar los archivos de configuración desde la copia fechada, volver a `APP_ENV=development` solo para desarrollo local y ejecutar `docker compose up -d app`. No tocar `centro_operativo.db`, `postgres_data` ni `postgres-backups`.
