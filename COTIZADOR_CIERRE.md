# Cierre del cotizador

Este documento reúne los casos de aceptación y el procedimiento de reversión
para la versión actual del cotizador.

## Casos de aceptación

| Caso | Datos sintéticos | Resultado esperado |
| --- | --- | --- |
| Manual asegurado | 27 km, sin móvil ni peajes | Base 2.140 + 2 km extra × 120; total 2.380 |
| Manual con móvil | 22 km + 10 km de salida | 32 km totales, 7 km excedentes |
| Peaje manual | 3 peajes, tarifa 416 | Peajes 1.248 y desglose manual |
| Peaje en ambos tramos | Mismo peaje detectado en móvil→origen y origen→destino | Dos pasadas y dos cargos independientes |
| Sin conexión | OSRM no responde | No se guarda precio; se ofrece pasar a distancia manual |
| Cambio de tarifa | Crear cotización, cambiar tarifa y recuperar la anterior | El historial conserva el snapshot y el precio original |
| Historial grande | Más de 50 registros | Paginación y filtros por texto, cobertura y modalidad |

Los casos automáticos usan coordenadas sintéticas y rutas simuladas en las
pruebas; no dependen de un servicio externo.

## Verificación ejecutada

- Suite local: 118 pruebas correctas.
- Integración PostgreSQL temporal: 22 pruebas correctas.
- Smoke visual WFM/Horarios: correcto con Playwright y Edge.
- Restauración temporal del último dump: `Status = OK`, 22 tablas, 0 restricciones inválidas y 0 problemas de secuencias.
- `node --check app/static/app.js` correcto.
- Health productivo: base, esquema y WFM en estado `ok`.

## Reversión controlada

La reversión solo debe recrear el contenedor de aplicación. No borrar el
volumen `postgres_data` ni ejecutar comandos de limpieza sobre PostgreSQL.

1. Identificar la imagen anterior con `docker image ls --no-trunc` o el digest
   guardado en el registro de despliegue.
2. Etiquetar ese digest como `librodetrabajo-app:latest`.
3. Ejecutar `docker compose up -d --no-build --no-deps app`.
4. Confirmar `http://127.0.0.1:8000/health` y que `db` y `backup` sigan saludables.

La migración de cotizaciones es aditiva: `pricing_snapshot` y
`postgres_core_v2` no eliminan datos existentes. El contrato histórico
`postgres_core_v1` debe conservarse.
