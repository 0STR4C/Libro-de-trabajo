# Registro de versiones

## 1.30.0 — 13 de septiembre de 2026 (Base técnica y despliegue seguro)

- Producción exige `PUBLIC_BASE_URL` con HTTPS y conserva FastAPI en loopback detrás de un proxy TLS, evitando sesiones inutilizables por cookies `Secure` sobre HTTP.
- Los servidores SQLite y PostgreSQL consumen metadatos, identidad, avisos y cotizador desde módulos compartidos; una prueba impide reintroducir la dependencia entre adaptadores.
- El registro SQLite incorpora checksums de migraciones históricas y ambos motores verifican que una migración aplicada no cambie; las pruebas cubren bases nuevas e inicialización repetida.
- `tools/test_all/run.ps1` unifica pruebas Python, sintaxis JavaScript, interfaz sintética, cobertura opcional y la suite PostgreSQL aislada obligatoria.
- Se documentaron arquitectura, desarrollo, datos locales excluidos de Git, acceso HTTPS y continuidad en otra computadora con cifras vigentes.

## 1.29.0 — 13 de septiembre de 2026 (Solicitudes WFM accesibles)

- Aprobar o rechazar una solicitud utiliza un único formulario con persona, tipo, fecha, motivo y comentario obligatorio, sin preguntas nativas consecutivas.
- Las ventanas dinámicas de Planificación anuncian su título, enfocan el primer control al abrir y devuelven el foco a la acción original al cerrar.
- El envío de una decisión queda bloqueado mientras se procesa y, ante un error, el formulario permanece disponible para corregir o reintentar.

## 1.28.0 — 13 de septiembre de 2026 (Flujos operativos guiados)

- Demoras reemplaza preguntas nativas consecutivas por formularios con contexto para renovar la vigencia o registrar la evidencia de normalización.
- La renovación ofrece plazos legibles de 1 a 24 horas y guarda la comprobación junto con el próximo control en una sola operación.
- Programados permite revisar y cambiar la tarea antes de crear una copia Sin asignar, explicando qué información se conserva y sin modificar el original.
- Tiempos de arribo presenta departamento, zona, prestación, tiempo y fuente antes de aprobar o rechazar una propuesta, y exige el fundamento dentro del mismo modal.

## 1.27.0 — 13 de septiembre de 2026 (Accesibilidad y adaptación)

- La navegación móvil funciona como un panel lateral que puede abrirse desde el encabezado y cerrarse con el fondo, al elegir un módulo o mediante Escape.
- Las tablas comunes conservan encabezados fijos en escritorio y se transforman en registros etiquetados en pantallas angostas, sin perder el significado de las columnas.
- Los formularios asocian automáticamente cada etiqueta con su control, identifican campos obligatorios, muestran errores junto al campo y restauran el foco al cerrar una ventana modal.
- Las pantallas anuncian su estado de carga, ofrecen reintento ante errores y los mensajes de éxito o fallo se comunican mediante regiones accesibles.
- La interfaz respeta `prefers-reduced-motion`, incorpora un enlace para saltar al contenido y hace visible el foco del teclado en controles interactivos.

## 1.26.0 — 13 de septiembre de 2026

- Configuración incorpora una pestaña **Novedades** con el historial completo de actualizaciones, ordenado desde la versión actual hasta la primera entrega.
- Cada versión puede desplegarse para consultar su fecha, descripción y lista de cambios sin reemplazar las novedades anteriores.
- La aplicación obtiene el historial del `CHANGELOG.md`, que se incluye también en la imagen Docker como fuente única del registro visible.

## 1.25.0 — 13 de septiembre de 2026

- El panel calcula tarjetas, métricas, gráficos y mapa desde un único contrato de backend, con instante de corte, zona horaria y versión de definiciones visibles.
- Pantalla y CSV usan los mismos filtros normalizados para avisos, demoras, programados y cotizaciones; cada reporte incorpora el ID estable de sus filas.
- Las demoras verificadas, pendientes de revisión y normalizadas se distinguen con el mismo alcance en la vista y en la exportación.
- Las exportaciones conservan los filtros visibles y generan un evento de auditoría con actor, cantidad de filas y parámetros aplicados.
- La auditoría incorpora ID de usuario, snapshots antes/después, correlación, origen, filtros operativos y protección contra actualización o eliminación.

## 1.24.0 — 12 de septiembre de 2026

- Programados incorpora agenda filtrable, responsables válidos, prevención de duplicados, estados Sin asignar → Asignado → En curso → Finalizado/Cancelado, evidencia de cierre e historial completo sin borrado físico.
- Las demoras tienen historial consultable de registro, verificaciones y normalización, con indicadores de verificación, evidencia de cierre y tiempo promedio de resolución.
- Las referencias de arribo conservan versiones, responsable y ciclo de revisión; las propuestas quedan pendientes hasta la aprobación de Supervisión y nunca se comunican antes de validarse.
- Se pueden definir prestaciones esperadas por zona y detectar brechas concretas de cobertura, junto con alertas de vencimiento y aprobación filtrables por responsable.
- Las pruebas SQLite usan una base temporal aislada por ejecución para permitir suites simultáneas sin colisiones.

## 1.23.0 — 10 de septiembre de 2026

- Demoras y referencias habituales de arribo comparten catálogos normalizados; se bloquean duplicados vigentes y cada normalización conserva responsable, fecha y evidencia de cierre.
- Las referencias de arribo incorporan estado (confirmada, provisional o sin referencia), fuente, vigencia y próxima revisión; la consulta operativa prioriza una demora vigente sobre cualquier tiempo habitual.
- Se agregó `/api/arrival-guidance` y la vista de referencias ahora separa visualmente una afectación actual de una orientación histórica, incluyendo advertencias de revisión vencida.
- La migración es aditiva para SQLite y PostgreSQL y conserva los registros existentes.
- Cada demora nueva define un plazo de control. Al vencer, deja de recomendarse al operador hasta que alguien confirme su vigencia o la normalice; ambas acciones quedan auditadas.
- El tablero cuenta por separado demoras verificadas y pendientes de revisión. Tiempos de arribo permite consultar por prestación y zona y solo recomienda referencias confirmadas, vigentes y con revisión al día.
- Los reportes de demoras incluyen última verificación, próxima revisión, responsable de normalización y evidencia de cierre.
- Las zonas usadas por demoras y referencias se registran en un catálogo operativo común, manteniendo compatibilidad con los textos históricos y ofreciendo sugerencias al consultar o editar.
- La cobertura de tiempos de arribo muestra por departamento y prestación qué referencias están vigentes, cuáles requieren revisión y dónde falta información, sin completar vacíos con tiempos supuestos.
- Cada referencia define responsable y ciclo de revisión; el tablero incorpora verificaciones, vencimientos próximos y tiempo promedio de resolución de demoras durante los últimos 30 días.
- La creación, reverificación y normalización de una demora genera eventos trazables para medir su ciclo de vida y conservar quién confirmó cada estado.
- Las nuevas cotizaciones guardan un snapshot de cobertura, categoría, modalidad, kilómetros incluidos, tarifa por kilómetro, base y peajes efectivos para reconstruir el precio histórico.
- Las distancias manuales aplican el mismo límite y validación en SQLite y PostgreSQL; editar un dato del formulario invalida el resultado anterior hasta volver a calcular.
- El conteo manual de peajes y el redondeo de importes/kilómetros quedan unificados entre SQLite y PostgreSQL, con redondeo comercial estable y límites consistentes.
- Las cotizaciones automáticas verifican de extremo a extremo el cobro de un mismo peaje en ambos tramos; si falla el servicio de rutas, la interfaz ofrece continuar con distancia manual sin guardar un precio incompleto.
- El contrato de esquema PostgreSQL actual se registra como `postgres_core_v2`, conservando el checksum histórico de instalaciones existentes y permitiendo migraciones aditivas seguras.
- El historial del cotizador incorpora paginación y filtros por texto, cobertura y modalidad; se documentan casos de aceptación, smoke visual y reversión controlada.
- Cada solicitud conserva la revisión y el turno publicados al enviarse. Una aprobación usa exclusivamente la publicación vigente, mantiene los borradores intactos y exige confirmación si el horario cambió durante la espera.
- Se rechazan solicitudes pendientes duplicadas para la misma persona y fecha. El agente puede cancelar una solicitud pendiente, y la cancelación permanece en el historial y en Auditoría.
- El agente ve envío, estado, fecha y responsable de resolución, comentario, horario original, revisión aplicada y horario resultante. El día afectado queda vinculado desde el calendario.
- Supervisión dispone de historial por estado y filtros por tipo, fecha, persona o motivo. Los Supervisores también pueden presentar y seguir solicitudes propias.
- El calendario personal muestra resumen semanal, descanso completo, horas extra, excepciones con horario y nota, continuidad nocturna, días libres publicados y origen de cada horario.
- Horarios integra publicaciones WFM y registros anteriores de `work_schedules`, evita duplicar días sustituidos, conserva nombres históricos y unifica la exportación CSV con la pantalla.
- El esquema se amplía de forma aditiva con revisión de origen, instantánea del turno y datos de cancelación; las instalaciones existentes conservan sus solicitudes.
- Se añadieron pruebas de migración, duplicados, cancelación, cambios de publicación, solicitudes propias de Supervisión e integración de horarios históricos.

## 1.22.0 — 10 de septiembre de 2026

- Las solicitudes aprobadas parten de la última publicación vigente; los borradores posteriores quedan intactos y la nueva revisión usa siempre el siguiente número disponible.
- Las ausencias que atraviesan una jornada partida se guardan como una excepción por bloque, y las excepciones superpuestas o con identificadores repetidos se rechazan.
- La publicación semanal previsualiza advertencias y revisiones por día, exige las revisiones esperadas y cancela la operación si otro supervisor modificó la semana.
- El CSV calcula las horas operativas por bloque y la API devuelve la cobertura normalizada para evitar divergencias entre servidor e interfaz.
- “Planificación de horarios” queda como nomenclatura única del módulo en navegación, pantalla y documentación.
- El arrastre muestra una copia semitransparente del turno completo, conserva el punto de agarre y comunica agente y franja exacta de destino.
- Agregar excepción inserta directamente una Reunión de 30 minutos; sus bordes permiten redimensionarla y el doble clic edita motivo y nota. El formulario completo permanece en el menú secundario.
- Cada publicación diaria, semanal o surgida de una solicitud aprobada reemplaza atómicamente la proyección definitiva en `wfm_published_plans` y `wfm_published_shifts`, preservando el historial append-only.
- Horarios del equipo consulta la proyección WFM publicada y representa entrada, salida, descanso, segmentos y excepciones; las revisiones publicadas anteriores siguen visibles mediante compatibilidad de lectura.
- Se agregaron pruebas de republicación, rollback, historial anterior, proyección de solicitudes y smoke de las nuevas interacciones.

## 1.21.0 — 9 de septiembre de 2026

- Cotizador: catálogo local de peajes administrable desde Configuración → Catálogos. Detecta estaciones activas cercanas a la geometría real de la ruta y suma una pasada por cada tramo: salida de grúa → origen y origen → destino.
- El desglose, cantidad, estaciones y tarifa efectiva de peajes queda inmutable en cada cotización, historial, resumen copiable y reporte CSV. Las cotizaciones manuales no inventan peajes porque no incluyen trazado geográfico.
- Tarifa por defecto tomada de Tarifas cotizador según cobertura; una estación puede definir excepcionalmente una tarifa propia. El catálogo puede desactivarse sin borrar el historial.
- No se activó Google Cloud, Maps, Places, Routes ni OAuth. Las fuentes públicas no permitieron extraer de forma verificable los marcadores del mapa compartido, por lo que no se sembraron coordenadas aproximadas.

## 1.20.0 — 9 de septiembre de 2026 (UI/UX Refactor)

- Nuevo Design System (SaaS Premium): Implementación de bordes redondeados (pill-shape), paleta de colores desaturados con contrastes sutiles y reducción drástica de ruido visual.
- Micro-interacciones en Gantt: Los bloques de turnos ahora cuentan con efectos de elevación al hacer hover, sombras suaves y transiciones de opacidad y escala al ser arrastrados.
- Integración de Excepciones: Las mermas (reuniones, licencias, etc.) se renderizan estéticamente inyectadas dentro de la barra principal compartiendo curvaturas y evitando aspecto de "parche".
- Limpieza cognitiva extrema: Eliminados los textos redundantes (ej: nombre de equipo repetido en vistas personales, columna de Rol colapsable en la grilla legacy si ya se está filtrando por el mismo).
- Menú Contextual estilizado: Sombras de alta profundidad y radios amplios, reemplazando completamente la botonera saturada de la columna de agentes.

## 1.19.1 — 9 de septiembre de 2026

- Corrección de física de Drag & Drop: el punto de agarre de excepciones utiliza el centro del bloque en gestos rápidos si falta el evento de presión previa.
- Integridad de excepciones al dividir o editar jornada: las mermas que cruzan el punto de corte o quedan huérfanas tras achicar un turno se filtran estrictamente por contención total, previniendo errores de guardado.
- Flujo de publicación seguro: la publicación semanal solicita confirmación antes de autoguardar cambios sucios en el borrador del día activo.
- Renderizado de menú contextual: posicionado mediante `requestAnimationFrame` para calcular su altura real y evitar recortes cerca del borde de la pantalla.
- Alertas de estado sucio (`dirty`): los avisos de navegación ("¿Descartar cambios?") solo se activan para administradores y planificadores, protegiendo la vista pasiva de los telefonistas.
- Búsqueda extendida en vista semanal: el filtro de la grilla legacy ahora evalúa el nombre del turno y las notas de cada bloque además del nombre de la persona.

## 1.19.0 — 9 de septiembre de 2026

- Publicación semanal atómica: un clic publica todos los borradores guardados de la semana seleccionada y conserva una revisión inmutable por día.
- El arrastre del turno conserva el punto exacto de agarre hasta ajustar la caída a la franja de media hora; la barra queda al 80 % de opacidad durante el gesto.
- Reuniones, capacitaciones, licencias y ausencias pueden desplazarse horizontalmente dentro de los bloques de trabajo sin alterar su duración.
- La columna de agentes muestra únicamente nombre, jornada total y horas extra; Editar, Dividir y Agregar excepción viven en un menú contextual por clic derecho o doble clic sobre el turno.
- Horarios queda como consulta de publicaciones, sin acciones de alta, edición o eliminación; su búsqueda filtra en vivo y al presionar Enter.
- La grilla semanal oculta personas sin coincidencias y evita repetir el rol junto al nombre cuando ya existe una columna de Rol.
- Las pruebas de navegador cubren punto de agarre, feedback visual, menú contextual, merma móvil, publicación semanal y búsqueda de Horarios.

## 1.18.1 — 9 de septiembre de 2026

- Cargados los horarios detallados de 20 Telefonistas para la semana ISO 37 (7–13 de septiembre de 2026), con entrada, salida y descanso por día.
- Las horas extra se conservan como dato explícito y la salida informada mantiene la extensión total de la jornada.
- Los turnos de cuatro horas sin descanso ya no reciben una pausa ficticia ni pierden cobertura operativa.
- Libre, Día por Estudio y Día por Cumpleaños se aplican sólo a la semana fechada y no se convierten en reglas recurrentes.
- La grilla y el CSV identifican horas extra y turnos sin descanso.
- La imagen Docker incluye únicamente la configuración WFM necesaria; no incorpora datos privados de onboarding.
- La planificación sigue cargando si la bandeja de solicitudes no está disponible y la API ya maneja respuestas de error no JSON sin romper la pantalla.

## 1.18.0 — 9 de septiembre de 2026

- Horizonte WFM de 72 franjas y atribución del turno nocturno al día en que comienza, con indicador visual `+1` para el día siguiente.
- Jornadas partidas mediante tijera, con hasta ocho bloques ordenados por persona y movimiento independiente de cada fragmento.
- Mermas por Reunión, Capacitación, Licencia y Ausencia superpuestas al turno; cada actividad tiene color propio y descuenta la cobertura operativa.
- Portal del agente para solicitar ausencia total/parcial o cambio de turno, con historial de estados.
- Bandeja de Supervisión para aprobar o rechazar solicitudes; una aprobación crea una revisión publicada nueva y actualiza la grilla.
- Compatibilidad en memoria con revisiones anteriores de 48 franjas y turnos de un solo bloque.
- Pruebas de dominio y navegador ampliadas para cruces de medianoche, corte, mermas y aprobación transaccional.

## 1.17.0 — 9 de septiembre de 2026

- Configuración global de WFM para duración de jornada y descanso, exclusiva del Administrador y aplicable a nuevos borradores.
- Demandas legacy incompletas completadas en memoria para eliminar `?` sin reescribir revisiones almacenadas hasta un guardado explícito.
- El descanso conserva su duración en cada turno y la cobertura/CSV/calendario personal la respetan.
- Guardados, sugerencias, publicaciones, requeridos semanales y reglas globales de WFM quedan registrados en Auditoría.
- Mapa de faltantes con rojo intenso, columna de agente más compacta y barra de turno alineada como bloque único.
- Vista semanal individual para Supervisión, limitada a horarios publicados y separada de la edición del borrador.
- Eliminados los entrypoints SQLAlchemy heredados sin referencias (`app/main.py`, `app/database.py`, `app/models.py`) y la dependencia no utilizada.

## 1.16.0 — 9 de septiembre de 2026

- Navegación WFM por semana ISO con año, número de semana y selector visual de los siete días.
- Plantilla base de horarios de Telefonistas derivada de las columnas históricas compartidas; vincula nombres/alias, mantiene un día libre inicial y deja fuera las licencias puntuales.
- Alta de turnos simplificada: los agentes seleccionados toman su horario base semanal y las personas sin patrón conservan un turno de referencia editable.
- La grilla muestra una barra única por turno: el arrastre mueve el bloque completo y el descanso se ajusta dentro de la barra, conservando las ventanas Telefonista 05:30–22:00 y Planificador 00:00–24:00.
- Pruebas ampliadas para plantilla semanal, semana ISO, barra completa y descanso arrastrable.

## 1.15.0 — 8 de septiembre de 2026

- Rediseño de Planificación de horarios: acciones agrupadas con la descarga CSV al extremo derecho, configuración semanal persistente de agentes requeridos y bloques separados para alta de turnos, cobertura y ajustes puntuales.
- Ventanas de planificación validadas y visibles por equipo: Telefonistas de 05:30 a 22:00 y Planificadores de 00:00 a 24:00; la barra completa del turno se puede mover por arrastre junto con el descanso.
- Navegación de supervisión agrupada en un desplegable propio, con Planificación de horarios y Registro de auditoría fuera del menú operativo.
- Identidad **Libro de Trabajo**, manteniendo Centro Operativo como descripción y conservando rutas y datos. Libro vectorial azul/turquesa y favicon ICO de 16 a 256 px.
- Nuevo ejecutable `tools/desktop_launcher/dist-libro/LibroDeTrabajo.exe` con icono integrado. Se conserva el ejecutable anterior y sus archivos.
- Herramienta de alta de Telefonistas con validación corporativa, comprobación previa, transacción, auditoría e idempotencia; contraseñas temporales comunes no expuestas, con hashes y sales independientes. Listado de entrada separado del código reutilizable.
- Verificación del restablecimiento de contraseñas por Administrador: ya existía en Configuración → Usuarios → Editar. No es necesario duplicar esa función.

## 1.14.0 — 8 de septiembre de 2026

- Planificación de horarios para Supervisor, conservando acceso completo del Administrador; equipos separados de Telefonistas, Planificadores y Supervisores.
- Jornada predeterminada corregida a **390 minutos totales: 180 operativos + 30 descanso + 180 operativos**. Alta múltiple, edición excepcional de jornada y descanso movible por arrastre o selector.
- Curva diaria de 48 franjas, cobertura fijada y diferencia con colores; demanda vacía se distingue de cero. Advertencias de excepciones sin impedir el ajuste manual dentro del turno.
- Sugerencia heurística de descansos que respeta los fijados; requiere demanda completa y no garantiza eliminar déficits.
- Borradores y publicaciones en revisiones inmutables, con autor/fecha y control de concurrencia. Calendario personal publicado de solo lectura y CSV del plan con columnas descriptivas.
- Rutas históricas de horarios restringidas: gestión solo Supervisor/Administrador, consulta de agentes limitada a su propia persona.
- Esquema aditivo `wfm_revisions`, compartido entre SQLite y PostgreSQL. No se migran ni reemplazan registros históricos. Primera entrega limitada a turnos dentro del mismo día; actividades adicionales y cruce de medianoche pendientes.
- Pruebas WFM aisladas, prueba UI sin red/datos reales y construcción candidata reutilizando dependencias locales en `tools/wfm_offline_build/`.

## 1.13.0 — 7 de septiembre de 2026

- Horarios ahora impide registros idénticos y turnos superpuestos para una misma persona, incluidos los cruces de medianoche. Los turnos consecutivos que comienzan exactamente al finalizar el anterior siguen permitidos.
- Se agregó **Copiar semana anterior** con alcance por persona o rol. La operación no reemplaza datos: copia solamente los horarios compatibles, omite los existentes o conflictivos y deja un resumen en auditoría.
- La grilla semanal permite agregar un horario directamente desde cada celda, precargando la persona y la fecha seleccionadas.
- PostgreSQL serializa las altas concurrentes por persona y fecha para evitar que dos supervisores creen el mismo horario al mismo tiempo; SQLite aplica el mismo control funcional dentro de una escritura bloqueada.
- La regresión quedó ampliada a 36 pruebas; el modo local ejecuta 28 y omite 8 dependientes del entorno. Además, 7 pruebas PostgreSQL pasaron sobre una base efímera aislada, incluidas copia idempotente, duplicados y superposiciones. `centro_operativo.db` se mantuvo intacta.
- Se conservó `tools/postgres_security_test/`, un ejecutor reproducible que monta las pruebas en solo lectura, usa PostgreSQL 16 sobre `tmpfs` y no conecta con el volumen operativo.

## 1.12.0 — 7 de septiembre de 2026

- Se incorporó **Horarios**, con registros semanales persistentes para Telefonistas, Planificadores y Supervisores.
- El equipo puede navegar semana a semana mediante una grilla visual, consultar el historial por persona, rol o período y descargar reportes CSV con columnas descriptivas.
- Supervisores, Planificadores y Administradores pueden crear, editar y eliminar horarios desde el módulo o desde el modal **Configuración → General → Horarios del equipo**. Telefonistas conservan acceso de consulta.
- El cotizador dejó de mostrar los campos de cerrajería «Desp. 22 hs» cuyo costo es cero; la información histórica queda preservada en la base para compatibilidad.

## 1.11.0 — 7 de septiembre de 2026

- Se incorporó configuración de producción con validación de secretos, hosts permitidos, límite de cuerpo, encabezados de seguridad y documentación OpenAPI deshabilitada por defecto.
- Las sesiones PostgreSQL usan cookies `HttpOnly`, `Secure` en producción, `SameSite=Strict`, CSRF, vencimiento absoluto y por inactividad, con revocación al cambiar contraseña o desactivar usuarios.
- Se agregaron límites progresivos para intentos fallidos de autenticación, respuestas genéricas y auditoría de ingresos correctos, fallidos y bloqueados.
- Se agregaron modelos Pydantic para validar entradas de autenticación, usuarios, permisos, tarifas y operaciones.
- Se corrigió la interacción de los botones internos: la CSP ya no bloquea las acciones dinámicas de la interfaz; se ejecutan mediante listeners seguros sin `eval` ni `unsafe-inline`.
- Se corrigió la migración de las nuevas tarifas PostgreSQL para que el contenedor pueda iniciar correctamente con su fila de resultados tipo diccionario.
- Se creó un lanzador gráfico Windows en `tools/desktop_launcher/` que inicia Docker Compose, espera la salud de la aplicación y abre el navegador sin tocar los volúmenes.
- El Administrador puede descargar el Registro de auditoría como CSV con fecha, registro, acción, usuario y detalle; el endpoint exige además el permiso de auditoría.
- El cotizador ahora exige una cobertura (Asegurado o No asegurado), deja Especial y Gavilán como categorías opcionales y muestra las tarifas en pestañas separadas por cobertura, con costos de mecánica, cerrajería, traslados, kilómetros, peajes y horas.
- Se normalizó el texto visible del menú y del encabezado a “Registro de auditoría”.
- Zonas con demora permite filtrar por período, estado, departamento, prestación y texto libre, con botones explícitos para aplicar o limpiar y descarga del reporte filtrado.
- Se documentaron la generación de `.env`, la rotación coordinada de credenciales, la restauración aislada y el acceso controlado dentro de la red local.
- El lanzador reconstruye el contenedor activo y se comprobó que sirve la nueva interfaz; queda pendiente la suite PostgreSQL de seguridad y una restauración de prueba separada antes de declararse entrega de producción. `centro_operativo.db` no fue reemplazada ni modificada.

## 1.10.0 — 4 de septiembre de 2026

- El 7 de septiembre de 2026 se reconstruyó el entorno Docker y se restauró, en un PostgreSQL nuevo y vacío, el último respaldo disponible cuya suma SHA-256 y catálogo fueron verificados.
- Se validaron los conteos recuperados, el ingreso, la lectura operativa, la exportación CSV, 12 pruebas automatizadas y la creación de un nuevo respaldo horario; `centro_operativo.db` permaneció en modo de solo lectura durante su comprobación.
- Se incorporaron filtros históricos de Avisos por período, estado, tarea, teléfono/contacto y texto libre.
- Administrador y Supervisor pueden descargar reportes de Avisos, Demoras, Programados y Cotizaciones como CSV compatibles con Excel y columnas descriptivas.
- Los valores exportados quedan protegidos frente a interpretación accidental como fórmulas.
- PostgreSQL genera respaldos horarios en formato `pg_dump`, valida cada catálogo y registra su SHA-256.
- Se documentó la diferencia entre persistencia inmediata, respaldo periódico y recuperación continua para producción.
- Las sesiones multiusuario se almacenan como hashes con vencimiento en PostgreSQL y pueden compartirse entre instancias de la aplicación.

## 1.9.0 — 4 de septiembre de 2026

- Se incorporó un backend PostgreSQL con paridad funcional respecto del servidor SQLite validado.
- Docker ahora ejecuta autenticación, roles, permisos, usuarios, auditoría, cotizador, tarifas y módulos operativos completos.
- Se agregó una migración conservadora de SQLite a PostgreSQL que abre el origen en modo de solo lectura y exige un destino vacío.
- Docker Compose incluye un perfil de migración y comprobación de salud de la aplicación.
- Se documentó una propuesta de conservación externa y restauración de respaldos.
- Se validó el despliegue real en Docker Desktop, se migraron las 12 tablas y se probaron lecturas y escrituras en PostgreSQL sin modificar SQLite.

## 1.8.0 — 4 de septiembre de 2026

- El modo local crea una copia de seguridad diaria y consistente de `centro_operativo.db` antes de inicializar la aplicación.
- Las copias se guardan en `backups/`, no reemplazan archivos existentes y no se eliminan automáticamente.
- Se agregó una prueba de regresión que verifica integridad, conservación del original y ausencia de sobrescritura.

## 1.7.0 — 2 de septiembre de 2026

- El mapa del resumen ahora considera exclusivamente demoras vigentes.
- La intensidad visual contempla la concentración de demoras en departamentos vecinos.
- Se incorporaron borde exterior y ayudas visuales personalizadas en los mapas.
- Tiempos de arribo pasó a una consulta interactiva por departamento, prestación y zona.
- El Log del sistema se movió al pie del menú y quedó reservado al Administrador por defecto.
- El rol Administrador conserva obligatoriamente todos los permisos.
- Se habilitó la creación de roles personalizados.
- El cotizador incorpora número de tarea, recuperación desde historial, borrador automático y copia del resumen.
- Se agregó visualización opcional de contraseñas en ingreso y administración de usuarios.
- El menú lateral queda fijo y mantiene siempre visibles Configuración y Log del sistema.

## 1.6.0 — 1 de septiembre de 2026

- Se incorporó correo corporativo obligatorio para usuarios.
- Se preparó el acceso opcional mediante Google Workspace.
- Se permitió el ingreso alternativo con correo o usuario y contraseña local.

## 1.5.0 — 1 de septiembre de 2026

- Se incorporó el cotizador automático y manual con tarifas configurables.
- Se agregó visualización de recorridos y cálculo de salida de la grúa.
- Se incorporaron métricas operativas y mapa departamental de Uruguay.

## 1.4.0 — 1 de septiembre de 2026

- Programados agrupados por tipo de traslado, con colores, estados editables, duplicación y eliminación.
- Se agregaron filtros operativos e historial de programados finalizados.

## 1.3.0 — 1 de septiembre de 2026

- Se incorporaron usuarios, roles y permisos configurables.
- Se definieron los roles iniciales Administrador, Supervisor, Planificador y Telefonista.

## 1.0.0 — 1 de septiembre de 2026

- Primera versión operativa con Avisos, Zonas con demora, Programados, Tiempos de arribo y trazabilidad.
- Persistencia en base de datos independiente de la planilla de origen.
