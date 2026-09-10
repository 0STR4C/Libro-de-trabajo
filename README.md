# Libro de Trabajo · Centro Operativo

La aplicación utiliza un libro azul/turquesa como identidad. Para abrirla desde
esta carpeta, usar **Libro de Trabajo.lnk** o
`tools/desktop_launcher/dist-libro/LibroDeTrabajo.exe`, con icono integrado.
Se conserva el ejecutable anterior. El nuevo EXE debe permanecer junto a sus
DLL y archivos de ejecución. Si se traslada el proyecto, regenerar el acceso
directo, porque apunta a la ubicación actual.

El Administrador puede restablecer contraseñas en **Configuración → Usuarios →
Editar → Nueva contraseña alternativa** (mínimo 12 caracteres). Dejar ese campo
vacío conserva la contraseña. También puede modificar nombre, correo, rol y
estado activo. Cambiar la contraseña revoca las sesiones existentes.

El 8/9/2026 se incorporaron las 39 personas del listado autorizado como
Telefonistas, con una contraseña temporal común no divulgada. Antes de entregar
accesos, el Administrador debe establecer las contraseñas definitivas. El listado
personal está separado del código en `data/onboarding/`; no incluirlo en paquetes
públicos. La herramienta reutilizable vive en `tools/user_onboarding/`.

Aplicación web desarrollada a partir del flujo observado en **Libro de trabajo - Febrero 2026.xlsx**. Reemplaza la operación diaria en planillas por registros estructurados en PostgreSQL.

## Módulos incluidos

### Planificación WFM (1.19.0)

En **Planificación de horarios**, Supervisor (y Administrador por su acceso
completo) elige día y equipo, abre «Crear turnos y configurar cobertura», selecciona
agentes y se les aplica el horario base semanal identificado para cada persona.
«Editar turno» permite ajustar jornadas excepcionales y marcar inicio o fin en el
día siguiente cuando corresponde.

Los agentes requeridos se configuran por día de la semana mediante una
configuración semanal persistente. Los valores iniciales son editables y se
aplican a fechas nuevas; las revisiones ya guardadas conservan su propia curva.
La planificación incorpora navegación por **semana ISO** (año, semana 1–53 y
días seleccionables). El horizonte de Telefonistas comienza a las **05:30** y
admite jornadas nocturnas hasta las **06:00 del día siguiente**. Las horas del
día siguiente aparecen con el indicador `+1`. Planificadores y Supervisores
disponen de un horizonte ampliado de 36 horas para excepciones nocturnas.

La demanda puede ajustarse por rango o por cada franja de media hora. Las
revisiones legacy con huecos se completan en pantalla con el requerido del día
sin reescribir la revisión almacenada; la interfaz ya no muestra signos de
interrogación y guarda cero explícito cuando el operador lo indica. La cobertura siempre cuenta únicamente al equipo
elegido. El turno completo se mueve desde el punto exacto donde se lo toma y el
descanso se arrastra dentro de su barra. Un clic derecho o doble clic sobre el
turno abre Editar, Dividir y Agregar excepción sin recargar la columna de agentes.
Las mermas también se arrastran horizontalmente dentro de los bloques de trabajo.
La semana seleccionada puede publicarse completa en una única operación atómica;
las excepciones al margen habitual de dos horas y los faltantes generan alertas.
«Sugerir descansos» requiere demanda completa y ofrece una mejora heurística,
no una garantía óptima.

**Guardar borrador no publica.** «Publicar día» y «Publicar semana completa» crean
revisiones nuevas; las anteriores conservan autor y fecha. Otro supervisor no
puede sobrescribir silenciosamente una revisión nueva. Los agentes consultan sus
horarios publicados por semana en Horarios, sin acceso a borradores ajenos. Esa
vista es de solo lectura y filtra por persona, turno o nota al escribir o pulsar Enter.
El supervisor puede dividir una jornada con la herramienta de tijera, mover cada
fragmento de forma independiente e insertar Reunión, Capacitación, Licencia o
Ausencia dentro del turno. Estas actividades se muestran con colores propios y
descuentan automáticamente la fila Operativos. Puede descargar el plan CSV con
los segmentos, excepciones y horas operativas resultantes.
También puede consultar la semana publicada de una persona concreta desde la
grilla, incluidos segmentos, mermas y continuaciones nocturnas.

Telefonistas y demás agentes planificables pueden solicitar una ausencia total
o parcial y un cambio de turno desde su calendario. Supervisión recibe las
peticiones en una bandeja por equipo. Aprobar genera una revisión publicada
nueva, actualiza el Gantt y conserva la revisión anterior; rechazar mantiene el
horario vigente. Ambos resultados quedan visibles para la persona solicitante.

El patrón inicial de telefonistas se conserva en
`data/wfm/telefonistas-horarios-semanales.json`. Se vincula por nombre/alias,
respeta un día libre semanal inicial y no incorpora licencias históricas como
reglas permanentes. El supervisor puede revisar y corregir cada barra antes de
guardar o publicar.

La carga fechada de la semana ISO 37 se conserva en
`data/wfm/telefonistas-horarios-2026-W37.json`. Para esos siete días prevalecen
la entrada, salida, descanso y horas extra informadas por persona. Los estados
Libre, Día por Estudio y Día por Cumpleaños sólo afectan esa semana; fuera de
ella continúa aplicándose el patrón base.

Almacenamiento aditivo: `wfm_revisions(plan_date, team, revision, published,
payload, actor_id, created_at)`, `wfm_weekly_requirements(team, weekday,
required, actor_id, updated_at)`, `wfm_settings(setting_key, value, actor_id,
updated_at)` y `wfm_requests`, que conserva solicitud, estado, resolución y la
revisión aplicada. El Administrador puede definir la jornada y el descanso estándar
desde Configuración → General; se aplican a futuros turnos y no reescriben
históricos. El payload conserva 72 franjas de media hora, los segmentos y las
excepciones validados del día como una instantánea coherente. No altera `work_schedules` ni la base
SQLite histórica protegida. Los registros previos continúan separados del nuevo
calendario WFM y accesibles para supervisores en la vista histórica existente.
Pendientes: integración del historial anterior en el calendario personal,
intercambio directo de turnos entre agentes y reglas de cupo/saldo de licencia.

Pruebas sin datos reales: `python -B -m unittest discover -s tests -q`;
`node tools/wfm_offline_build/ui_smoke.cjs` (ver requisitos en esa carpeta).

### Módulos operativos

### Peajes locales en el cotizador

No requiere Google Cloud. El Administrador carga las estaciones en
**Configuración → Catálogos → Peajes del cotizador**, con nombre y coordenadas
precisas (en Google Maps, clic derecho sobre el punto y copiar coordenadas).
Se puede usar la tarifa general de la pestaña correspondiente de Tarifas del
cotizador o definir una tarifa particular para una estación.

En cotizaciones automáticas, se compara cada estación activa con la geometría de
cada recorrido mediante una tolerancia de 300 metros. Una estación se cobra una
vez por tramo; por lo tanto, si la salida de la grúa y el traslado principal
cruzan el mismo peaje, se registran dos pasadas. El sistema no agrega peajes a
cotizaciones manuales porque no posee la ruta. Toda cotización conserva cantidad,
nombre, tramo y precio efectivo aunque el catálogo cambie después.

Antes de usarlo para comunicar precios, cargá y verificá todas las estaciones
que apliquen. El catálogo no se precargó con coordenadas estimadas: el mapa
compartido no permitió exportar sus marcadores desde el entorno de trabajo y no
se deben inventar posiciones de cobro.

- Avisos y seguimientos, con estados controlados.
- Zonas con demora y normalización.
- Traslados programados por fecha, hora, origen, destino y prestador.
- Horarios del equipo en grilla semanal e historial por persona, rol y período, con control de superposiciones y copia de semanas.
- Tiempos estándar de arribo consultables.
- Panel con indicadores operativos.
- Cotizador de servicios por distancia, con salida opcional del móvil, reglas tarifarias configurables e historial.
- Registro de auditoría de altas, ediciones y cambios de estado.
- API documentada automáticamente en `/docs` durante desarrollo; en producción la documentación queda deshabilitada salvo habilitación explícita.

La versión actual es **1.19.0**. El detalle de cada entrega se mantiene en [CHANGELOG.md](CHANGELOG.md) y también se resume dentro de **Configuración → General**.

La aplicación **no lee ni escribe Excel durante su funcionamiento**. La planilla fue utilizada solamente para relevar los procesos y definir el modelo inicial.

## Puesta en marcha

### Opción sencilla en Windows

Haga doble clic en **Abrir Centro Operativo.bat**. Se inicia un modo local con base de datos SQLite y el navegador se abre automáticamente. No cierre la ventana negra mientras utiliza la herramienta; para detenerla, cierre esa ventana. Los datos quedan guardados en `centro_operativo.db` y no dependen de Excel.

Este modo facilita el uso en el equipo actual. La versión de despliegue requerida continúa disponible en Docker Compose y utiliza PostgreSQL.

### Copias de seguridad

Al iniciar el modo local, la aplicación crea en `backups/` una copia consistente de `centro_operativo.db`. Se conserva como máximo una copia nueva por fecha y nunca se reemplaza una copia ya existente. Las copias antiguas no se eliminan automáticamente; deben conservarse o archivarse según la política operativa definida por la organización.

En Docker/PostgreSQL, cada alta o actualización se confirma inmediatamente en la base persistente. Además, el servicio `backup` genera cada hora un `pg_dump` verificado en `postgres-backups/`, junto con su SHA-256. El intervalo se configura mediante `BACKUP_INTERVAL_SECONDS`; el mínimo admitido es cinco minutos. No se eliminan copias automáticamente.

### Primer ingreso

- Usuario: `admin`
- Contraseña inicial: `admin1234`

Al ingresar, use **Configuración** para crear los usuarios del equipo y asignarles uno de los roles iniciales: Administrador, Supervisor, Planificador o Telefonista. Cada usuario debe tener un correo terminado en `@portoservicios.com.uy`; no se admiten cuentas personales ni de otros dominios. Desde **Configuración → Tarifas cotizador** puede cambiar, mediante pestañas separadas, los costos para asegurados y no asegurados (mecánica ligera, especiales, cerrajería, traslados, kilómetros, peajes y horas). Los campos de cerrajería desp. 22 hs con costo cero se conservan para compatibilidad, pero ya no se muestran en la configuración. Los cambios no modifican cotizaciones anteriores. Cambie la contraseña inicial antes de una puesta en producción.

### Activar el ingreso con Google Workspace

El sistema permite usar la cuenta corporativa de Google sin guardar la contraseña de Google. Para activarlo una sola vez:

1. En Google Cloud, crear o seleccionar un proyecto de la organización.
2. Configurar la pantalla de consentimiento OAuth como **Interna**.
3. Crear un ID de cliente OAuth de tipo **Aplicación web**.
4. Agregar `http://localhost:8000` y `http://127.0.0.1:8000` como orígenes de JavaScript autorizados.
5. Copiar el ID terminado en `.apps.googleusercontent.com` en **Configuración → Acceso Google**.
6. En **Configuración → Usuarios**, asignar el correo corporativo a los usuarios existentes.

No se debe copiar ni guardar un secreto de cliente. En el primer ingreso con Google, la herramienta vincula la identidad verificada con el usuario activo que tenga el mismo correo. El dominio se valida nuevamente en el servidor y un correo corporativo que no haya sido autorizado previamente en **Usuarios** tampoco puede ingresar. Como contingencia, el formulario alternativo admite el correo corporativo o el nombre de usuario junto con la contraseña local.

El cálculo automático de distancia utiliza una ruta vehicular y requiere conexión a Internet. El cotizador también ofrece una carga manual de kilómetros para contingencias o enlaces que no incluyan coordenadas. La cobertura siempre queda definida como **Asegurado** o **No asegurado**; por defecto se selecciona Asegurado. **Especial** y **Gavilán** son categorías opcionales y excluyentes.

### Opción Docker/PostgreSQL

El contenedor ejecuta `app/postgres_server.py`, que mantiene las mismas rutas, autenticación, permisos, cotizador y módulos operativos que el modo local.

Para migrar los registros actuales, el volumen PostgreSQL debe estar vacío. La herramienta abre `centro_operativo.db` en modo de solo lectura:

1. Copiar `.env.example` como `.env` y cambiar las contraseñas.
2. Ejecutar:

   ```powershell
   docker compose --profile migration run --rm migrate
   docker compose up --build -d app
   ```

3. Abrir `http://localhost:8000`.
4. Verificar salud en `http://localhost:8000/health`. La API aparece en `http://localhost:8000/docs` solo cuando `ENABLE_API_DOCS=true`; en producción se mantiene deshabilitada por defecto.

Para detener sin perder datos:

```powershell
docker compose down
```

Los datos quedan en el volumen Docker `postgres_data`. `docker compose down -v` elimina ese volumen y, por lo tanto, la base completa.

Para una instalación nueva que no importe los registros SQLite, omita el primer comando y ejecute directamente `docker compose up --build -d app`.

La migración se niega a operar si encuentra filas en PostgreSQL. Esto evita mezclar o sobrescribir información. Su código y documentación se conservan en `tools/sqlite_to_postgres/`.

### Ejecutable de escritorio

Se incluye un lanzador gráfico para Windows en `tools/desktop_launcher/dist/CentroOperativo.exe`. Al abrirlo, comprueba Docker Desktop, reconstruye e inicia `app`, espera `/health` y abre el navegador. No ejecuta migraciones ni elimina volúmenes. Requiere .NET 8 Desktop Runtime y que el ejecutable permanezca dentro de esta carpeta del proyecto o una subcarpeta para localizar `compose.yaml`. El código fuente y el procedimiento de compilación están en [tools/desktop_launcher/README.md](tools/desktop_launcher/README.md).

### Seguridad y acceso remoto privado

El backend PostgreSQL incluye configuración separada para desarrollo y producción: en producción exige secretos no predeterminados, limita el host y el tamaño de las solicitudes, usa cookies de sesión `HttpOnly` con protección CSRF, vencimiento absoluto y por inactividad, revocación al cambiar credenciales y límites progresivos de intentos de ingreso. PostgreSQL no publica ningún puerto y la aplicación se enlaza únicamente a `127.0.0.1:8000`.

La guía [SECURITY.md](SECURITY.md) explica la generación segura de `.env`, la rotación coordinada de credenciales, las sesiones y la restauración aislada de respaldos. La guía [DEPLOY_REMOTE_PRIVATE.md](DEPLOY_REMOTE_PRIVATE.md) describe el acceso privado mediante Tailscale Serve sin Funnel, sin abrir el router y sin instalar ni configurar Tailscale automáticamente. No se debe marcar `HTTPS_CONFIRMED=true` hasta comprobar el acceso HTTPS real.

### Estado de esta computadora

El 7 de septiembre de 2026 se reconstruyeron los contenedores y se restauró en un volumen PostgreSQL nuevo el respaldo verificado `postgres-backups/centro_operativo_20260905T043730Z.dump`. Se validaron la aplicación, el ingreso, la lectura de registros, la exportación CSV y un nuevo respaldo automático. Los servicios `app`, `db` y `backup` quedaron activos. En esta computadora no vuelva a ejecutar la migración sobre el volumen actual: para iniciar o reanudar el servicio use solamente:

```powershell
docker compose up -d app
```

La aplicación queda disponible en `http://127.0.0.1:8000/`. No opere alternativamente sobre SQLite y PostgreSQL: después de elegir PostgreSQL como base activa, toda la operación debe continuar allí para evitar dos historiales divergentes. `centro_operativo.db` y sus copias se conservan como origen protegido y respaldo de la migración.

### Credenciales definitivas

Las credenciales de los operadores son los usuarios y contraseñas con los que ingresan a Centro Operativo. Además existen credenciales técnicas que no deben conocer los operadores:

- `POSTGRES_PASSWORD`: contraseña usada exclusivamente entre la aplicación y PostgreSQL.
- `APP_SECRET`: secreto largo usado por el servidor para proteger el hash de las sesiones compartidas entre instancias.
- `ADMIN_PASSWORD`: contraseña inicial de contingencia del Administrador.
- El ID OAuth de Google, si la organización habilita ese ingreso.

En esta computadora se mantienen valores de desarrollo para la validación local. Antes de instalar en un servidor deben generarse valores aleatorios distintos, guardarse en el gestor de secretos del servidor y excluirse del repositorio, documentación, respaldos y registros visibles.

Las sesiones PostgreSQL se conservan como hashes con vencimiento, no como tokens legibles. Esto permite que más de una instancia de la aplicación atienda a los usuarios sin perder la sesión en cada reinicio. `SESSION_SECONDS` define la duración; el valor de desarrollo es 12 horas.

### Reportes para supervisión

Administrador y Supervisor pueden descargar reportes de Avisos, Demoras, Programados, Horarios y Cotizaciones como CSV compatibles con Excel. El Administrador también puede descargar el Registro de auditoría. Cada archivo usa encabezados descriptivos y evita que textos operativos se interpreten como fórmulas.

Avisos incluye filtros por fecha desde/hasta, estado, número de tarea, teléfono o contacto y texto libre. Demoras permite filtrar por fecha desde/hasta, estado (vigente, normalizada o todas), departamento, prestación y texto libre; el reporte descargado conserva esos filtros. Programados respeta tarea, fecha y vista de finalizados. **Horarios** conserva cada registro por fecha y semana, permite navegar semana a semana, consultar el historial por persona o rol y descargar el resultado. Desde cada celda se puede precargar una fecha y persona; **Copiar semana anterior** respeta el filtro de persona o rol y omite, sin reemplazar, registros duplicados o superpuestos. Los turnos nocturnos pueden finalizar al día siguiente. Los usuarios activos de Telefonista, Planificador y Supervisor se cargan desde **Configuración → General → Horarios del equipo** mediante un modal. Cotizaciones permite descargar el historial con distancias, desglose de precios, tipo de servicio y usuario que cotizó.

## Modelo de datos

- `notices`: avisos, comunicaciones y seguimientos.
- `delay_zones`: demoras activas e históricas.
- `scheduled_transfers`: agenda normalizada de traslados.
- `work_schedules`: horarios por persona, fecha y semana, con historial y rol de la asignación.
- `arrival_standards`: tiempos de referencia.
- `audit_events`: trazabilidad inmutable desde la interfaz.
- `users`, `roles` y `role_permissions`: acceso por usuario, roles y permisos configurables.
- `quote_rules`: tarifas vigentes del cotizador.
- `quotes`: historial de cotizaciones y su desglose.

## Próximos pasos sugeridos antes de producción

- Cargar el histórico que se decida conservar mediante una migración única.
- Ejecutar y documentar una restauración de prueba en una base PostgreSQL temporal separada; la suite PostgreSQL de seguridad ya puede repetirse con `tools/postgres_security_test/run.ps1`.
- Definir credenciales definitivas, configurar HTTPS privado, copias externas con retención y monitoreo.
- Cambiar la contraseña inicial del Administrador y coordinar, en una ventana de mantenimiento, cualquier rotación de la contraseña del rol PostgreSQL.
- Validar con el equipo los catálogos definitivos de estados, prestaciones y departamentos.
