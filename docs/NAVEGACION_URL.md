# Navegación por URL

El catálogo de rutas, títulos, nombres de menú y permisos vive en
`frontend/routes.js`. El shell React usa la URL como fuente de la sección activa.
Abrir una dirección directamente, refrescar, usar Atrás/Adelante o abrir el enlace
del menú en otra pestaña conserva el destino. `/` se convierte en `/resumen`.

| Sección | Ruta |
| --- | --- |
| Resumen | `/resumen` |
| Avisos | `/avisos` |
| Cotizador | `/cotizador` |
| Zonas con demora | `/demoras` |
| Programados | `/programados` |
| Horarios | `/horarios` |
| Mis solicitudes | `/solicitudes` |
| Dashboard de Supervisión | `/supervision/dashboard` |
| Auditoría de demoras | `/supervision/auditoria-demoras` |
| Planificación de horarios | `/supervision/planificacion` |
| Auditoría general | `/supervision/auditoria` |
| Configuración, roles por defecto | `/configuracion` |
| General | `/configuracion/general` |
| Tiempos estándar | `/configuracion/tiempos-estandar` |
| Novedades | `/configuracion/novedades` |
| Usuarios | `/configuracion/usuarios` |
| Roles y permisos | `/configuracion/roles` |
| Acceso Google | `/configuracion/acceso-google` |
| Tarifas | `/configuracion/tarifas` |
| Catálogos | `/configuracion/catalogos` |

Parámetros opcionales permitidos, validados al abrir una dirección:

| Rutas | Parámetros |
| --- | --- |
| Avisos | `view`, `status`, `from`, `to` |
| Cotizador | `tab` (`new`/`history`) |
| Demoras | `view`, `from`, `to`, `department`, `service` |
| Programados | `view`, `status`, `from`, `to` |
| Horarios | `week` (lunes ISO `AAAA-MM-DD`), `view` (`team`/`mine`) |
| Planificación | `day` (`AAAA-MM-DD`), `team` |
| Auditoría de demoras | `scope`, `from`, `to`, `department` |
| Auditoría general | `from`, `to`, `entity`, `action` |
| Tiempos estándar | `department`, `service`, `status` |

Fechas inválidas, valores fuera de catálogo y parámetros no reconocidos se
descartan. Teléfonos, búsquedas libres, nombres, detalles de casos y borradores
no se escriben en la URL. Los borradores conservan sus mecanismos actuales.
Las consultas de API siguen usando los filtros locales completos; solo se
sincronizan a la dirección los parámetros no sensibles indicados arriba.

El servidor PostgreSQL y el servidor SQLite sirven `index.html` en las rutas de
interfaz sin extensión; React resuelve la vista y muestra una página comprensible
si la ruta no existe o el usuario no tiene permiso. `/api/*`, `/static/*`,
archivos inexistentes, descargas y `/health` conservan sus respuestas propias.
Las rutas no sustituyen la autorización de las API.

En producción, el proxy HTTPS debe reenviar **la ruta original completa** al
puerto de la aplicación, además de conservar el host y las cookies. No necesita
reescribir `/programados` a `/`: la aplicación ya responde a esa ruta. Si el
proxy actual solo reenvía `/`, Sistemas debe ampliar el proxy para enviar las
rutas de interfaz y también `/api`, `/static` y `/health` al mismo backend.
Conservar el nombre Compose, los volúmenes, `.env` y el puerto configurado.
