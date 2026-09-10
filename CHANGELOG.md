# Registro de versiones

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

- Rediseño de Planificación WFM: acciones agrupadas con la descarga CSV al extremo derecho, configuración semanal persistente de agentes requeridos y bloques separados para alta de turnos, cobertura y ajustes puntuales.
- Ventanas de planificación validadas y visibles por equipo: Telefonistas de 05:30 a 22:00 y Planificadores de 00:00 a 24:00; la barra completa del turno se puede mover por arrastre junto con el descanso.
- Navegación de supervisión agrupada en un desplegable propio, con Planificación de horarios y Registro de auditoría fuera del menú operativo.
- Identidad **Libro de Trabajo**, manteniendo Centro Operativo como descripción y conservando rutas y datos. Libro vectorial azul/turquesa y favicon ICO de 16 a 256 px.
- Nuevo ejecutable `tools/desktop_launcher/dist-libro/LibroDeTrabajo.exe` con icono integrado. Se conserva el ejecutable anterior y sus archivos.
- Herramienta de alta de Telefonistas con validación corporativa, comprobación previa, transacción, auditoría e idempotencia; contraseñas temporales comunes no expuestas, con hashes y sales independientes. Listado de entrada separado del código reutilizable.
- Verificación del restablecimiento de contraseñas por Administrador: ya existía en Configuración → Usuarios → Editar. No es necesario duplicar esa función.

## 1.14.0 — 8 de septiembre de 2026

- Planificación WFM para Supervisor, conservando acceso completo del Administrador; equipos separados de Telefonistas, Planificadores y Supervisores.
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
- Se documentaron la generación de `.env`, la rotación coordinada de credenciales, la restauración aislada y el acceso privado mediante Tailscale Serve.
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
