# Acceso desde la red local

La aplicación se ejecuta en Docker. Para compartirla con otras PCs, el acceso
público debe usar HTTPS mediante un proxy TLS de la organización. FastAPI queda
escuchando en `127.0.0.1:8000` detrás de ese proxy. PostgreSQL continúa dentro
de la red Docker y no publica su puerto.

## Preparación

1. Copiar `.env.example` como `.env` y completar los secretos sin compartirlos.
2. Definir un nombre DNS para el servidor y configurar el proxy TLS para enviar
   tráfico a `http://127.0.0.1:8000`.
3. Reemplazar `<NOMBRE_DNS_DEL_SERVIDOR>` en `PUBLIC_BASE_URL`,
   `ALLOWED_HOSTS` y `ALLOWED_ORIGINS`. El origen debe coincidir exactamente
   con `https://<NOMBRE_DNS_DEL_SERVIDOR>`.
4. Crear y validar previamente una imagen con etiqueta inmutable.
5. Iniciar la aplicación:

   ```powershell
   docker compose -f compose.yaml -f compose.production.yaml up -d --no-build --wait
   docker compose ps
   ```

   `app` debe mostrar `127.0.0.1:8000->8000/tcp` y `db` no debe mostrar puertos
   publicados.

6. Desde el servidor, comprobar `http://127.0.0.1:8000/health`.
7. Desde otra PC de la LAN, abrir `https://<NOMBRE_DNS_DEL_SERVIDOR>/` y
   comprobar que el certificado sea válido.

Si otra PC no puede conectarse, comprobar primero la conectividad de red y las
reglas del firewall del servidor según la política de la organización. Este
proyecto no modifica el firewall automáticamente.

## Producción local

Para usar la configuración endurecida:

```powershell
docker compose -f compose.yaml -f compose.production.yaml up -d --no-build --wait
```

La configuración de producción exige secretos y una `PUBLIC_BASE_URL` HTTPS,
deshabilita la documentación API y requiere declarar hosts y orígenes. Si no
hay HTTPS, el proceso se detiene antes de abrir la base: una cookie `Secure` no
puede sostener una sesión sobre HTTP.

## Comprobación

```powershell
docker compose ps
Invoke-WebRequest https://<NOMBRE_DNS_DEL_SERVIDOR>/health
```

No ejecutar `docker compose down -v`: eliminaría el volumen PostgreSQL.
