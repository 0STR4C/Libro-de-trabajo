# Tiempos estándar de llegada

La administración está en **Configuración → Tiempos estándar de llegada**. Las lecturas requieren `standards.view`; crear, editar, activar y desactivar exigen `arrival_times.manage`. El historial de cambios se conserva en `audit_events`. Resumen consulta solo filas activas sin `seed_key`; las filas sintéticas de pruebas se retiran al publicar la matriz. Ninguna operación de este catálogo crea Avisos o modifica Zonas con demora.

## Indicaciones y ámbitos

Cada fila tiene una prestación (`ML`, `SINIESTROS` o `GRÚA`), departamento y ámbito geográfico. `zone = "Todo el departamento"` es el alcance general. Una zona individual o una agrupación canónica de zonas se guarda en `zone`; sus integrantes se conservan además en `zone_members`. El selector incluye el catálogo geográfico existente y localidades/barrios adicionales legibles en las capturas aportadas el 16/10/2026. Esas capturas verifican **nombres de ubicaciones**, no asignaciones de minutos. El mapa agrega las zonas configuradas a su selector, aun si no figuraban en el catálogo inicial.

`indication_type` define el significado del tiempo:

| Tipo | Campos | Texto operativo |
| --- | --- | --- |
| `TIME` | `base_estimated_minutes` | `30 min habituales` (compatibilidad con valores unitarios anteriores) |
| `MAXIMUM` | `minutes_max` | `Máximo de 30 min` |
| `INTERVAL` | `minutes_min`, `minutes_max` | `Entre 30 y 45 min` |
| `TO_CONFIRM` | ninguno | `A confirmar` |

Los campos que no corresponden al tipo deben ser `null`; el intervalo tiene mínimo y máximo ordenados. Un `TIME` heredado no se interpreta como máximo ni promedio. El API y PostgreSQL validan las formas y los minutos (1–1440). No se permite publicar dos referencias específicas activas de la misma prestación y departamento que compartan una zona; esta comprobación se serializa entre altas concurrentes. Un valor departamental puede coexistir con uno específico.

## Resolución de una consulta

Para una prestación, departamento y zona, primero se busca la referencia exacta, luego una agrupación que contenga esa zona y finalmente `Todo el departamento`. Las referencias de otra prestación no participan. Una consulta de `Todo el departamento` usa solo la referencia departamental. Desactivar una referencia específica deja disponible la general, si existe; sin ambas, la respuesta indica `not_configured`. El catálogo no se combina con demoras: una afectación vigente aplicable ocupa la indicación mostrada por Resumen y oculta el estándar, incluso si requiere revisión. Al normalizar, vuelve a mostrarse el estándar.

`GET /api/arrival-times/resolve?service=ML&department=MONTEVIDEO&zone=Pocitos` devuelve `status` (`configured`/`not_configured`), `service`, `department`, `requested_zone`, `indication_type`, `base_estimated_minutes`, `minutes_min`, `minutes_max`, `display_text`, `unit` (`minutes`), `scope` (`zone`/`group`/`department`/`null`), `source_zone`, `source_zones`, `arrival_time_id`, `revision` y `updated_at`. Si falta configuración, tipo, valor y origen son `null` y `source_zones` es vacío. Un error de consulta o un parámetro inválido no se presenta como ausencia. `GET /api/arrival-times/department?department=MONTEVIDEO` conserva la lectura por departamento para otros clientes; `GET /api/arrival-times` sigue paginado a 50 para Configuración.

Para el panel de un solo clic, `GET /api/arrival-times/overview` entrega `{departments: {"MONTEVIDEO": [...], ...}}`, con los 19 departamentos y solo referencias activas operativas. Usa `standards.view`, el mismo permiso de lectura de Resumen, y no requiere permiso de edición. Resumen carga este contrato junto al estado de demoras antes de habilitar la consulta: muestra tres prestaciones por departamento, agrupa las localidades que comparten una misma referencia y agrega el respaldo general como «Resto del departamento». Cuando una demora específica afecta una localidad dentro de un grupo, esa localidad se separa visualmente y la indicación habitual permanece solo para las demás. Una demora departamental reemplaza el grupo completo. Si el catálogo o las demoras fallan, no se confirma un tiempo a partir de datos antiguos.

## Matriz operativa publicada

`python -m tools.seed_arrival_times.official_matrix` muestra el plan sin escribir. Para publicarlo se usa `--apply --backup-to <ruta-dentro-del-proyecto>`. El script conserva primero en JSON las filas sintéticas existentes, luego las retira y publica la matriz en una sola transacción. Registra cada alta oficial en la auditoría. Es idempotente; si una fila oficial cambió manualmente o existe una referencia operativa específica superpuesta, cancela la publicación en vez de sobrescribirla.

La matriz autorizada para este cambio establece:

| Ubicación | Mecánica Ligera | Grúa |
| --- | --- | --- |
| Montevideo: Centro, Parque Rodó, Pocitos, Punta Carretas, Tres Cruces, Mercado Modelo, Buceo, Punta Gorda | Máximo de 30 min | Máximo de 45 min |
| Montevideo: Maroñas, Malvín | Máximo de 30 min | Máximo de 45 min |
| Montevideo: Nuevo París, Cerro, Colón, Casavalle, Peñarol, La Teja, Manga | Máximo de 45 min | Máximo de 45 min |
| Canelones: Ciudad de la Costa | Máximo de 45 min | Máximo de 45 min |
| Canelones: localidades del corredor hasta Peaje Solís listadas en el script | Máximo de 45 min | Máximo de 60 min |
| Maldonado Ciudad y Piriápolis | Entre 30 y 45 min | Máximo de 60 min |
| Ciudades cabecera del interior enumeradas en el script | Máximo de 60 min | Máximo de 60 min |

Para los 18 departamentos distintos de Montevideo, el respaldo departamental es **A confirmar** en las tres prestaciones, conforme a la regla explícita “En interior, lo que no figura: A confirmar”. Una referencia específica prevalece sobre ese respaldo. No se infiere un tiempo numérico de Siniestros para las zonas enumeradas ni un respaldo departamental de Montevideo: donde no hay valor publicado, la API responde `not_configured`. El corredor de Canelones se representa mediante las localidades expresamente enumeradas; el sistema no infiere una cobertura vial continua por coordenadas. `ML` se conserva como identificador de datos y se muestra como **Mecánica Ligera** en la interfaz de consulta.

