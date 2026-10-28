# Auditoría técnica y operativa — 28/10/2026

## Alcance y composición

La aplicación tiene dos adaptadores HTTP: `app/local_server.py` para SQLite local y
`app/postgres_server.py` para FastAPI con PostgreSQL. Comparten reglas de negocio
en `app/` y sirven el mismo frontend React. `frontend/routes.js` concentra rutas,
títulos y permisos; `frontend/app-shell.jsx` gestiona sesión, navegación,
actualización y tema. Vite compila React 18, PrimeReact 10 y Tailwind 3 hacia
`app/static/frontend/`. `frontend/visual-system.css` define la escala visual
transversal; las vistas conservan su composición operativa en JSX. Docker Compose
mantiene aplicación, PostgreSQL y respaldos locales.

Los módulos recorridos fueron Resumen, Avisos, Cotizador, Zonas con demora,
Programados, Horarios, Mis solicitudes, Supervisión, WFM, auditorías y
Configuración. La revisión combinó código, pruebas automáticas, auditoría de
dependencias y navegador con datos sintéticos. No incluyó datos operativos reales
ni una prueba de intrusión externa.

## Hallazgos corregidos

| Prioridad | Hallazgo | Corrección y evidencia |
| --- | --- | --- |
| Alta | Un enlace de Google Maps podía redirigir la solicitud del servidor a un host no autorizado. | `app/identity.py` valida HTTPS, host y puerto en cada redirección. Prueba de destinos internos y externos en `tests/test_quote_geography.py`. |
| Alta | `npm audit` detectó dos avisos altos y uno moderado en dependencias de compilación; `pip-audit` detectó avisos de Starlette. | Vite 7.3.7, `source-map-js` 1.2.2, `postcss-selector-parser` 6.1.5, FastAPI 0.162.0 y Starlette 1.10.0. Ambas auditorías terminaron sin avisos conocidos. |
| Media | Una ruta API inexistente en SQLite intentaba abrir la base antes de responder 404. | La ruta se rechaza antes de consultar SQLite. `tests/test_spa_routes.py` y la suite de dominio pasan. |
| Media | En Avisos a 1280 px, el estado y el encabezado Acciones se partían y reducían la lectura rápida. | Se redistribuyó el ancho de la tabla y el encabezado de acciones usa un icono con nombre accesible. Una aserción de navegador exige que la etiqueta de estado ocupe una línea. |
| Baja | La documentación afirmaba que no existía una prueba de navegador React y fijaba un número de vistas desactualizado. | `README.md` y `tools/test_all/README.md` indican el ejecutor vigente; el resultado de `run.ps1` remite a él. |

## Interfaz y uso operativo

La jerarquía visual es coherente: barra lateral azul marino, acción primaria azul,
estados semánticos, títulos y controles en la escala común. Las pantallas
priorizan consulta y acción en la misma vista. Resumen muestra mapa e indicación
por prestación; Avisos presenta cola, filtros y acciones en una tabla compacta.
Las pruebas de navegador cubren 1920, 1536 y 1280 px, tema oscuro, zoom de 125 %,
menús, diálogos y navegación. En el recorrido probado no hubo desbordamiento
horizontal de página. La matriz semanal conserva desplazamiento interno.

La densidad está justificada en Avisos, Demoras y auditorías; allí conviene dar
ancho a estado, tarea e instrucción comunicable antes que a columnas auxiliares.
El mapa del Resumen ocupa más altura que el panel de indicaciones cuando hay
pocos datos; es espacio deliberado para reconocer departamentos y afectaciones,
sin impedir la lectura de la respuesta operativa junto al mapa. No se retiraron
archivos históricos como `app/static/app.js` ni `legacy_archive/`: aún los usan
herramientas de compatibilidad y pruebas antiguas, aunque no forman parte del
runtime React publicado.

## Verificación

- `tools/test_all/run.ps1`: 176 pruebas de dominio aprobadas, 7 históricas
  omitidas, 89 pruebas PostgreSQL aisladas aprobadas, sintaxis JS y Vite aprobados.
- `tools/browser_interaction/run.cjs`: 20 escenarios React aprobados con respuestas
  sintéticas, incluida la lectura del estado de Avisos a 1280 px.
- `npm audit` y `pip-audit -r requirements.txt`: sin vulnerabilidades conocidas
  en las versiones resueltas el día de la revisión.
- `docker compose build app`, `docker compose up -d --no-deps app`, `/health`:
  imagen reconstruida, servicio iniciado y respuesta HTTP 200.

## Próximas mejoras operativas propuestas

1. **Cola de Avisos por turno y responsable.** Mostrar primero los casos sin
   responsable y en espera que requieren un rellamado, con vencimiento acordado
   por el equipo. Mantener la fecha y el motivo visibles para evitar abrir cada
   aviso. No convertir Avisos en alertas automáticas.
2. **Control de calidad de instrucciones de demora.** En Demoras, destacar la
   prestación, ubicación, vigencia e instrucción literal antes de guardar y
   mostrar una vista previa de cómo aparecerá en Resumen. Esto reduce mensajes
   ambiguos al telefonista sin alterar la precedencia actual.
3. **Estado de frescura de los datos.** Mostrar la hora de última lectura válida
   y el fallo de actualización junto a cada vista crítica. Resumen ya diferencia
   fallos de ausencia de demoras; conviene extender esa claridad a otras colas
   que se consultan durante el turno.
4. **Indicadores de carga de trabajo.** Medir avisos pendientes por antigüedad,
   demoras que requieren revisión y solicitudes WFM por resolver. Usar esos
   indicadores para priorizar trabajo, no para reemplazar el detalle de casos.

## Límites pendientes

Las pruebas visuales usan datos inventados y no certifican todas las
combinaciones de permisos, contenido largo o navegadores. La suite general aún
ejecuta Vite con una imagen local separada, que debe reconstruirse cuando cambie
`package-lock.json`; el Dockerfile de la aplicación reconstruye su propia etapa
frontend. Antes de publicar una entrega, conviene repetir el recorrido con
usuarios de cada rol y datos anonimizados de volumen representativo.
