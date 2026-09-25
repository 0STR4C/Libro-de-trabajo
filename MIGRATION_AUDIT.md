# Auditoría de migración React · 24 de septiembre de 2026

## Estado comprobado en el código

Las diez rutas declaradas en `app/static/app.js` (`dashboard`, `notices`,
`quotes`, `delays`, `transfers`, `schedules`, `standards`, `settings`, `audit` y
`wfm`) invocan funciones de montaje de `frontend/main.jsx`. Ese archivo expone
el mismo contrato en `window.LibroTrabajoUI` y `window.ReactApp`. Los módulos
de `frontend/` no usan `DomSlot`, `innerHTML` ni `dangerouslySetInnerHTML`. El
inicio de sesión también se monta como `LoginView` React. `app/static/app.js`
ya no inyecta plantillas HTML ni interpreta atributos de eventos inline.

La aplicación completa **todavía no es 100 % React**: `index.html` contiene
sidebar, header, selector de apariencia y el contenedor de contenido; `app.js`
controla el enrutado, la visibilidad por permisos, el tema, la navegación móvil
y el montaje de cada vista. `branding.js` modifica el shell mediante DOM. El
archivo `app/static/wfm.js` conserva la interfaz histórica para
`tools/wfm_offline_build/ui_smoke.cjs`, pero `index.html` no lo carga y el
runtime usa `frontend/wfm.jsx`. La prueba offline histórica no verifica la
vista React actual.

| Ruta | Implementación activa | Observación funcional |
| --- | --- | --- |
| Resumen | `frontend/dashboard.jsx` | Alertas con estado local; SVG React. |
| Avisos | `frontend/operations.jsx` | Filtros, estados, duplicados, asignación, comentarios e historial en React. |
| Cotizador | `frontend/quotes.jsx` | Cálculo, borrador, historial y Leaflet encapsulado en React. |
| Zonas con demora | `frontend/operations.jsx` | Filtros, verificación y normalización en React. |
| Programados | `frontend/transfers.jsx` | Alta, duplicados, transiciones, edición e historial en React. |
| Horarios | `frontend/schedules.jsx` | Grilla publicada, historial, vista personal y solicitudes en React. |
| Tiempos de arribo | `frontend/standards.jsx` | Mapa, referencias, cobertura, aprobación e historial en React. |
| Configuración | `frontend/settings.jsx` | Usuarios, roles, tarifas y catálogos en React. |
| Auditoría | `frontend/audit.jsx` | Filtros y cambios antes/después en React. |
| Planificación WFM | `frontend/wfm.jsx` | Línea de tiempo editable, cobertura, publicación, semana personal y solicitudes en React; falta verificar interacción en navegador. |

## Reglas recuperadas y contrastadas

- Los permisos son del servidor; la UI muestra acciones según los permisos
  otorgados. En Avisos, `notices.assign` habilita Asignar/Reasignar, sin
  restringirlo artificialmente al rol Supervisor.
- El alta de Avisos consulta duplicados abiertos antes de guardar. El cierre
  exige motivo; los cambios exitosos recargan la grilla sin recargar la página.
- Las tarifas se separan por cobertura. Los campos históricos de cerrajería
  después de las 22 con valor cero se conservan en el modelo, pero se ocultan
  en el formulario. Las reglas de kilómetros incluidos y bases asegurado/no
  asegurado permanecen editables. El cálculo y sus validaciones viven en la API.
- Horarios muestra datos publicados de WFM y registros históricos; la carga de
  turnos ocurre en Supervisión. La API antigua de copia semanal sigue
  disponible, pero no forma parte de la vista React actual.
- Una solicitud WFM aprobada sobre una publicación posterior requiere una
  segunda confirmación explícita; cancelar una solicitud solo se ofrece si
  está pendiente. La cobertura visible se recalcula al editar el borrador y
  la publicación semanal presenta las advertencias de cada día. Los datos se
  validan en el servidor.
- Las directivas de diseño y de ejecución vigentes siguen en `AGENTS.md` y
  `CLAUDE.md`, cuyo contenido debe mantenerse idéntico.

## Brechas comprobadas antes de declarar paridad completa

1. `frontend/wfm.jsx` ya tiene siete botones diarios, una línea de tiempo React
   con arrastre de bloques, descansos y excepciones, ajuste de los bordes de
   excepciones, acceso al editor con clic derecho o doble clic y alta rápida de
   reuniones. Debe comprobarse en navegador que estos gestos preservan el
   comportamiento fino de la implementación histórica, incluida la vista
   previa de arrastre y la navegación por teclado.
2. La vista personal de `frontend/schedules.jsx` distingue días sin
   publicación, días libres publicados y continuaciones nocturnas; muestra
   horas planificadas, operativas y extra. La bandeja WFM filtra solicitudes por
   estado, tipo, fecha, persona y motivo. Deben verificarse los cálculos con
   turnos partidos, nocturnos y excepciones reales o sintéticas.
3. No existe una prueba interactiva autenticada de todas las rutas React en
   esta auditoría. `vite build` y la comprobación de sintaxis verifican el
   bundle, pero no prueban el funcionamiento de cada flujo de negocio.
4. La migración del shell y del enrutador será necesaria si «100 % React»
   incluye toda la aplicación y no solo las rutas de contenido.

El pulido visual pantalla por pantalla puede tomar Avisos como plantilla, pero
la paridad WFM y la decisión sobre el shell deben resolverse antes de declarar
cerrada la migración estructural completa.
