# Verificación de producción

`verify-production.ps1` comprueba una instalación ya ejecutándose sin iniciar,
detener ni recrear contenedores. Valida el Compose de producción, que `app` y
`db` estén activos, que `/health` responda y que exista un respaldo reciente
con checksum válido.

Desde la raíz del proyecto:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\deployment\verify-production.ps1
```

Entradas: el proyecto Compose activo, `/health` y `postgres-backups/`.
Salida: resultado `OK` o un error con la comprobación que falló. Solo lee
configuración, estado de Docker, el endpoint de salud y respaldos.

Antes de usarlo en producción, definir las variables requeridas por
`compose.production.yaml`, incluyendo `APP_IMAGE`, `APP_BIND_ADDRESS`,
`APP_SECRET`, `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`, `ALLOWED_HOSTS` y
`ALLOWED_ORIGINS`. Nunca pega secretos en la línea de comandos ni los imprime.
