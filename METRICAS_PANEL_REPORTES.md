# Contrato de métricas, panel y reportes

Estado: contrato vigente; etapas de implementación completadas.

Versión del contrato: 1.0  
Fecha: 2026-09-12  
Ámbito: panel operativo, reportes CSV y registro de auditoría de Libro de Trabajo.

## Objetivo

Este documento define qué significa cada indicador, cuál es su fuente y cómo
deben aplicarse los períodos y filtros. La misma definición debe controlar el
backend, la interfaz y los archivos exportados.

El panel ayuda a decidir qué necesita atención ahora. Los análisis históricos
se presentan como métricas de período y no se mezclan con el estado actual.

## Convenciones comunes

- La fuente operativa principal es PostgreSQL. El modo SQLite debe conservar la
  misma semántica para cada indicador y filtro.
- `as_of` es el instante único de cálculo generado por el servidor. Todos los
  componentes de una respuesta deben usar ese mismo instante.
- Los instantes se almacenan y calculan en UTC. Las fechas visibles y los filtros
  diarios se interpretan en `America/Montevideo`.
- Un período de fechas es semiabierto: desde las 00:00 de `date_from`, inclusive,
  hasta las 00:00 del día siguiente a `date_to`, exclusivo, convertido a UTC.
- El período móvil predeterminado es `[as_of - 30 días, as_of]`.
- Las métricas de estado actual no tienen límite temporal. Las métricas de
  período indican explícitamente qué fecha del registro determina su inclusión.
- La paginación limita las filas mostradas, pero nunca modifica `total_count`,
  distribuciones, indicadores o exportaciones.
- Los porcentajes sin filas en el denominador devuelven `null` y la interfaz
  muestra **Sin datos**. Un conjunto vacío no equivale a 100 %.
- Las consultas deben usar estados canónicos. Los estados históricos de
  traslados se normalizan antes de filtrar o agrupar:
  `PENDIENTE → SIN_ASIGNAR`, `CONFIRMADO → ASIGNADO` y
  `COMPLETADO → FINALIZADO`.
- Cada respuesta agregada incluye `as_of`, `timezone`, `period_start` cuando
  corresponda y `definitions_version`.

## Estados canónicos

### Avisos

- Abiertos: `PENDIENTE`, `EN_GESTION`, `ESPERANDO_RESPUESTA`.
- Terminales: `RESUELTO`, `CANCELADO`.

### Demoras

- Registrada como vigente: `status = VIGENTE`.
- Verificada y comunicable: `status = VIGENTE` y
  `review_due_at > as_of`.
- Requiere revisión: `status = VIGENTE` y
  `review_due_at <= as_of`.
- Cerrada: `status = NORMALIZADO`.
- `review_due_at` usa `expires_at`; si falta, utiliza
  `last_verified_at + 120 minutos` y, si también falta,
  `created_at + 120 minutos`.

### Traslados programados

- Pendientes de coordinación: `SIN_ASIGNAR`, `ASIGNADO`, `EN_CURSO`.
- Terminales: `FINALIZADO`, `CANCELADO`.

## Indicadores principales del panel

| ID | Nombre visible | Definición canónica | Fuente | Período y filtros |
|---|---|---|---|---|
| `notices_open` | Avisos que requieren gestión | Cantidad de avisos cuyo estado canónico es abierto. | `notices`, una fila por aviso. | Foto a `as_of`; sin filtro de fecha. |
| `delays_current` | Demoras verificadas | Cantidad de demoras vigentes cuyo control no venció a `as_of`. | `delay_zones`, una fila por demora. | Foto a `as_of`; sin filtro de fecha. |
| `delays_need_review` | Demoras que requieren revisión | Cantidad de demoras vigentes cuyo control venció a `as_of`. | `delay_zones`. | Foto a `as_of`; sin filtro de fecha. |
| `transfers_pending` | Programados pendientes | Cantidad de traslados en `SIN_ASIGNAR`, `ASIGNADO` o `EN_CURSO`, después de normalizar estados históricos. | `scheduled_transfers`, una fila por traslado. | Foto a `as_of`; sin filtro de fecha. |

Estos cuatro valores deben calcularse en el servidor. Los gráficos y tarjetas no
deben volver a calcularlos a partir de listas paginadas o limitadas.

## Indicadores de control de demoras

El período predeterminado es de 30 días y puede cambiarse entre 1 y 365 días.

| ID | Nombre visible | Numerador o fórmula | Denominador | Fecha que determina el período |
|---|---|---|---|---|
| `delays_created` | Creadas en el período | Cantidad de demoras creadas. | No aplica. | `delay_zones.created_at`. |
| `delays_normalized` | Normalizadas en el período | Cantidad de cierres realizados. | No aplica. | `delay_zones.normalized_at`. |
| `delay_verifications` | Verificaciones en el período | Eventos `VERIFICADO`. | No aplica. | `delay_events.created_at`. |
| `delays_expiring_30m` | Vencen en 30 min | Demoras comunicables con `0 < review_due_at - as_of <= 30 minutos`. | No aplica. | Foto a `as_of`; no depende del período histórico. |
| `average_resolution_minutes` | Resolución promedio | Promedio de `normalized_at - created_at`, en minutos, para cierres del período. | Demoras normalizadas en el período. | `delay_zones.normalized_at`. |
| `verified_active_percentage` | Demoras verificadas | `delays_current / (delays_current + delays_need_review) × 100`. | Todas las demoras con `status = VIGENTE` a `as_of`. | Foto a `as_of`; no depende del período histórico. |
| `normalized_with_evidence_percentage` | Cierres con evidencia | Cierres del período con `resolution_note` no vacío. | Todos los cierres del período. | `delay_zones.normalized_at`. |
| `standards_overdue` | Referencias vencidas | Referencias activas cuya disponibilidad es `REVIEW_DUE`. | No aplica. | Fecha local correspondiente a `as_of`. |

Las cantidades se muestran como enteros. Los promedios y porcentajes se
redondean a un decimal solo para presentación; el cálculo usa la precisión
completa disponible.

## Distribuciones y alertas del panel

| Elemento | Universo canónico | Agrupación | Regla de presentación |
|---|---|---|---|
| Demoras verificadas por departamento | Todas las demoras incluidas en `delays_current`. | Departamento canónico. | Mapa completo, sin límite silencioso. |
| Departamentos afectados ahora | Mismo universo anterior. | Departamento canónico. | Mostrar los cinco primeros e indicar “5 de N” cuando existan más. |
| Estado de avisos | Todos los avisos abiertos a `as_of`. | Estado canónico. | No mezclar cerrados históricos con la carga operativa actual. |
| Estado de programados | Todos los programados pendientes a `as_of`. | Estado canónico normalizado. | Incluir `SIN_ASIGNAR`, `ASIGNADO` y `EN_CURSO`. |
| Alertas de demoras | Demoras que requieren revisión o vencen en 30 minutos. | Responsable y urgencia. | Vencidas antes de próximas a vencer. |
| Alertas de referencias | Propuestas pendientes y referencias con revisión vencida o dentro de 14 días. | Responsable y urgencia. | Vencidas antes de próximas a vencer; filtro “asignadas a mí” por identidad estable. |

## Contrato de filtros y exportaciones

La vista y el CSV deben usar el mismo objeto de filtros normalizado y la misma
función de consulta. El CSV contiene todas las filas que cumplen esos filtros;
la vista puede paginarlas. El contador visible informa el total filtrado y no el
tamaño de la página actual.

| Reporte | Grano y fuente | Fecha del filtro | Filtros canónicos |
|---|---|---|---|
| Avisos | Una fila por aviso, `notices`. | `created_at`. | `date_from`, `date_to`, `status`, `scope`, `task`, `contact`, `q`. `scope`: `open`, `unassigned`, `mine`, `waiting`, `all`. El servidor obtiene la identidad para `mine`; no confía en un nombre enviado por el navegador. |
| Demoras | Una fila por demora enriquecida, `delay_zones`. | `created_at`. | `date_from`, `date_to`, `scope`, `department`, `service`, `q`. `scope`: `current`, `review`, `normalized`, `all`. |
| Programados | Una fila por traslado, `scheduled_transfers`. | `scheduled_date`. | `date_from`, `date_to`, `status`, `transfer_type`, `provider`, `responsible`, `task`, `q`. `status=ACTIVE` representa los tres estados pendientes. |
| Horarios | Una fila por turno publicado, proyección WFM y revisiones publicadas compatibles. | `schedule_date`. | `week` o `date_from/date_to`, `employee_id`, `role`, `q`. Nunca incluir borradores. |
| Cotizaciones | Una fila por cotización, `quotes`. | `created_at`. | `date_from`, `date_to`, `q`, `coverage`, `mode`, `created_by`. Los filtros visibles se aplican también al CSV. |
| Auditoría | Una fila por evento, `audit_events`. | `created_at`. | `date_from`, `date_to`, `entity`, `entity_id`, `action`, `actor_id`, `q`. Orden estable por `created_at DESC, id DESC`. |

Todo reporte debe conservar encabezados descriptivos, UTF-8 con BOM, separador
`;` y protección frente a fórmulas de planilla. Una exportación debe registrar
tipo de reporte, actor, instante, período y filtros aplicados, sin copiar datos
sensibles al detalle de auditoría.

## Contrato mínimo de auditoría

El registro general debe permitir responder: quién realizó la acción, cuándo,
sobre qué registro y qué cambió.

Campos requeridos para nuevos eventos:

- `id`: identificador único y ordenable.
- `created_at`: instante UTC asignado por el servidor.
- `actor_id`: usuario estable; puede ser nulo solo para eventos del sistema o
  intentos de autenticación sin usuario identificado.
- `actor_name`: copia del nombre visible en el momento del evento.
- `entity`: tipo canónico de entidad.
- `entity_id`: identificador estable; puede ser nulo en eventos globales.
- `action`: acción perteneciente a un catálogo controlado.
- `before`: JSON con los campos relevantes anteriores.
- `after`: JSON con los campos relevantes posteriores.
- `detail`: explicación legible, sin secretos ni contraseñas.
- `correlation_id`: agrupa todos los eventos de una misma operación.
- `source`: `web`, `migration`, `system` o `test`.

Para eliminaciones, `before` conserva la instantánea mínima necesaria. Para
permisos, tarifas, horarios, avisos y traslados, `before` y `after` incluyen los
campos modificados. Los eventos de WFM referencian fecha, equipo y revisión; no
utilizan siempre `entity_id = 0` como única identificación.

La aplicación no ofrece actualización ni eliminación de eventos. En producción,
el rol usado por la aplicación debe tener `INSERT` y `SELECT`, pero no `UPDATE`
ni `DELETE`, sobre el registro de auditoría, salvo un procedimiento administrativo
separado y documentado.

## Guardrails de confiabilidad

- Paridad: conteo y claves de las filas filtradas en pantalla coinciden con el
  CSV para los mismos parámetros.
- Completitud: todo cambio persistente relevante produce al menos un evento de
  auditoría dentro de la misma transacción.
- Identidad: todo evento realizado por un usuario autenticado conserva
  `actor_id`.
- Vigencia: el panel incluye `as_of` y todas las reglas temporales usan ese valor.
- Volumen: ningún KPI o distribución depende de los límites de una lista.
- Trazabilidad: una exportación queda auditada con sus filtros.
- Privacidad: contraseñas, hashes, tokens y secretos nunca aparecen en `before`,
  `after`, `detail` ni archivos exportados.

## Pruebas de aceptación de las etapas siguientes

1. Crear datos sintéticos con cada estado permitido y verificar los cuatro
   indicadores principales mediante consultas independientes.
2. Probar los límites exactos de vigencia: un vencimiento igual a `as_of`
   pertenece a “requiere revisión”.
3. Comprobar períodos con registros justo antes, dentro y después de sus bordes,
   incluyendo la conversión de `America/Montevideo` a UTC.
4. Verificar que `normalized_at`, y no `created_at`, controle las métricas de
   cierres y tiempo de resolución.
5. Comprobar que los estados históricos de traslados producen el mismo resultado
   que sus equivalentes canónicos.
6. Comparar IDs y cantidad total entre pantalla y CSV para cada combinación de
   filtros, con más filas que el tamaño de una página.
7. Confirmar que horarios muestra y exporta únicamente revisiones publicadas.
8. Verificar denominadores vacíos: porcentajes `null` y texto “Sin datos”.
9. Validar que crear, editar, cambiar estado, publicar, eliminar y exportar deja
   un evento con identidad y diferencia suficientes.
10. Ejecutar las pruebas generales y la suite PostgreSQL aislada definida en
    `tools/postgres_test_db/run.ps1` cuando comience la modificación de código.

## Estado de implementación

La etapa 2 centralizó en el backend los indicadores y distribuciones del panel.
La respuesta usa un solo `as_of`, expone la versión del contrato y la zona
horaria, calcula los cierres por `normalized_at`, devuelve `null` para
porcentajes sin denominador y no depende de listas limitadas. El panel base se
puede consultar con el permiso `dashboard.view` sin permisos adicionales.

La etapa 3 unificó los filtros de pantalla y CSV para avisos, demoras,
programados y cotizaciones. Los archivos incluyen el ID estable de cada fila,
usan la fecha local de `America/Montevideo` y conservan los filtros visibles.

La etapa 4 amplió la auditoría con `actor_id`, `actor_name`, `before_data`,
`after_data`, `correlation_id` y `source`. Las exportaciones generan eventos con
sus parámetros y cantidad de filas. SQLite y PostgreSQL rechazan actualizaciones
y eliminaciones sobre `audit_events`.

La etapa 5 agregó pruebas automáticas de límites temporales, estados heredados,
denominadores vacíos, paridad de exportación, identidad del actor, snapshots,
exclusión de secretos e inmutabilidad. No quedan diferencias conocidas dentro
del alcance definido para panel, exportaciones y auditoría.

## Decisiones pendientes

- No se fijan objetivos numéricos hasta reunir una línea base operativa de al
  menos cuatro semanas con estas definiciones estables.
- Operaciones debe confirmar si “Programados pendientes” debe abarcar todo el
  futuro o mostrar además cortes separados para vencidos, hoy y próximos siete
  días. Hasta esa decisión, el indicador conserva todos los estados no
  terminales sin límite de fecha.
- Operaciones debe acordar la política de conservación y acceso administrativo
  al registro de auditoría.
