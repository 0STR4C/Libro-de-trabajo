# Acceso desde la red local

La aplicación se ejecuta en Docker y queda disponible para otras PCs de la
misma red mediante el puerto 8000. PostgreSQL continúa dentro de la red Docker
y no publica su puerto.

## Preparación

1. Copiar `.env.example` como `.env` y completar los secretos sin compartirlos.
2. Reemplazar `<NOMBRE_O_IP_LAN_DEL_SERVIDOR>` en `ALLOWED_HOSTS` y
   `ALLOWED_ORIGINS` por el nombre DNS o la IPv4 fija del servidor.
3. Iniciar la aplicación:

   ```powershell
   docker compose up --build -d app
   docker compose ps
   ```

   `app` debe mostrar `0.0.0.0:8000->8000/tcp` y `db` no debe mostrar puertos
   publicados.

4. Desde el servidor, comprobar `http://127.0.0.1:8000/health`.
5. Desde otra PC de la LAN, abrir
   `http://<NOMBRE_O_IP_LAN_DEL_SERVIDOR>:8000/`.

Si otra PC no puede conectarse, comprobar primero la conectividad de red y las
reglas del firewall del servidor según la política de la organización. Este
proyecto no modifica el firewall automáticamente.

En esta computadora la IPv4 LAN detectada es `192.168.1.8`. Como fue asignada
por DHCP, conviene reservarla en el router o actualizar `.env` si cambia.

## Producción local

Para usar la configuración endurecida:

```powershell
docker compose -f compose.yaml -f compose.production.yaml up --build -d
```

La configuración de producción exige secretos, deshabilita la documentación
API y requiere declarar explícitamente hosts y orígenes de la LAN.

## Comprobación

```powershell
docker compose ps
Test-NetConnection -ComputerName <NOMBRE_O_IP_LAN_DEL_SERVIDOR> -Port 8000 -InformationLevel Quiet
```

No ejecutar `docker compose down -v`: eliminaría el volumen PostgreSQL.
