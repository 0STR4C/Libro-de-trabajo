# Plan de mejora UI/UX

Este documento registra el orden de trabajo y el criterio de verificación de la
interfaz de Libro de Trabajo. Las mejoras preservan la identidad, los permisos y
los datos operativos existentes.

Las etapas marcadas «completada» documentan verificaciones históricas de la
interfaz anterior. La [auditoría React vigente](MIGRATION_AUDIT.md) enumera la
paridad que falta comprobar o recuperar, especialmente en Planificación WFM.

## Fuente de diseño para próximas mejoras · UUPM

El 23/09/2026 se verificó la presencia de UI UX Pro Max en
`.claude/skills/ui-ux-pro-max/`, con instrucciones, referencias, scripts y
catálogos locales. Es una herramienta para orientar el desarrollo de interfaz;
su incorporación no modifica las pantallas ni revalida las etapas históricas
registradas más abajo.

Cada nueva tarea UI/UX debe comenzar leyendo su `SKILL.md` y revisando el estado
actual de la pantalla. Elegir una consulta enfocada, comprobar que los resultados
correspondan al problema y registrar las reglas aplicadas o las excepciones
justificadas. Las prioridades son accesibilidad, interacción, legibilidad,
consistencia y rendimiento, preservando la identidad de Libro de Trabajo.

El procedimiento, requisitos y ejemplos están en
[`tools/ui_ux_guidance/README.md`](tools/ui_ux_guidance/README.md). El mensaje inicial
reutilizable de **11 · Interfaz y experiencia de uso** está en
[`tools/ui_ux_guidance/PROMPT_11.md`](tools/ui_ux_guidance/PROMPT_11.md).
Las áreas funcionales que modifiquen interfaz deben seguir el mismo procedimiento.

La revisión del 23/09/2026 no encontró un `design-system/` persistido. La primera
propuesta global deberá contrastarse con los estilos existentes antes de adoptarla.
No se deben generar sistemas visuales distintos por conversación.

## Etapa 0 — Base y trazabilidad · completada

- Se relevó el estado del repositorio antes de editar y se preservaron los
  cambios concurrentes existentes.
- Configuración separa **General** de **Novedades**.
- Novedades obtiene del `CHANGELOG.md` el historial completo de versiones.
- El historial se verifica con versiones sintéticas y dentro de una imagen
  Docker candidata sin red.

## Etapa 1 — Navegación y adaptación · completada

- En móvil, la navegación lateral se abre desde el encabezado y no reduce el
  ancho del contenido.
- Puede cerrarse con el fondo, con Escape o al elegir un módulo.
- La página incorpora enlace para saltar al contenido y marca el módulo activo
  mediante `aria-current`.
- Se verifica a 390 px que no exista desborde horizontal.

## Etapa 2 — Formularios y errores · completada

- Las etiquetas se asocian automáticamente con inputs, selectores y áreas de
  texto generados dinámicamente.
- Los campos obligatorios se identifican visualmente y mediante
  `aria-required`.
- Los errores de validación aparecen junto al control y los errores del servidor
  permanecen visibles dentro del modal.
- Los envíos se bloquean mientras están en curso para evitar registros dobles.

## Etapa 3 — Tablas y lectura operativa · completada

- En escritorio, los encabezados permanecen visibles durante el desplazamiento.
- En pantallas angostas, cada fila se presenta como un registro etiquetado con el
  nombre original de cada columna.
- Las tablas conservan navegación por teclado y una región con nombre accesible.

## Etapa 4 — Mensajes, modales y teclado · completada

- Los mensajes de éxito y error se anuncian con regiones vivas y permanecen más
  tiempo cuando requieren corrección.
- Los modales enfocan el primer control, mantienen acciones visibles al recorrer
  formularios largos y devuelven el foco al botón de origen al cerrar.
- Todos los controles muestran foco visible y la interfaz respeta la preferencia
  de movimiento reducido.
- Los fallos de carga ofrecen una acción de reintento en la misma pantalla.

## Etapa 5 — Verificación y entrega · completada en cada versión

- Pruebas estáticas de estructura y contratos de interfaz.
- Navegador sin red con API y datos sintéticos para escritorio y móvil.
- Suite general del proyecto.
- Suite PostgreSQL con base efímera aislada.
- Imagen candidata sin descargas y despliegue local del servicio `app` después
  de verificar salud, versión e historial.

## Próximas iteraciones por pantalla

La base común ya está aplicada. Las próximas conversaciones pueden profundizar
Avisos, Demoras, Programados, Cotizador, Horarios, Planificación, Auditoría y
Configuración por separado, midiendo cantidad de pasos y tiempos de cada tarea
con escenarios sintéticos propios de cada módulo.
