# Arquitectura técnica

El catálogo único de rutas React, títulos y permisos está en `frontend/routes.js`.
`frontend/app-shell.jsx` sincroniza la sección y filtros no sensibles con History
API. Ambos adaptadores HTTP entregan `index.html` para rutas de interfaz sin
extensión, preservando los 404 de API y recursos estáticos. El proxy de producción
reenvía la ruta original al servicio de aplicación; véase
[`docs/NAVEGACION_URL.md`](docs/NAVEGACION_URL.md).

## Ejecución

Centro Operativo ofrece dos adaptadores HTTP. `app/local_server.py` usa SQLite
para el modo de escritorio local. `app/postgres_server.py` usa FastAPI y
PostgreSQL para la operación multiusuario en Docker. Ambos sirven la interfaz de
`app/static/` y deben conservar el mismo comportamiento funcional.

Los adaptadores dependen de módulos compartidos y no deben importarse entre sí:

- `application.py`: versión, permisos y roles iniciales;
- `identity.py`: correo corporativo, Google y coordenadas/rutas;
- `notices.py`: estados, permisos de actualización y duplicados;
- `quotes.py`: catálogo, límites y redondeos del cotizador;
- `dashboard.py`, `delays.py`, `transfers.py`, `scheduling.py`, `reporting.py`,
  `tolls.py` y `wfm.py`: reglas de los dominios operativos;
- `security.py`: secretos, contraseñas, CSRF y límites de autenticación;
- `migrations.py`: checksums y compatibilidad del registro de migraciones.

Las consultas y transacciones específicas permanecen en cada adaptador. Una
regla nueva debe entrar primero en un módulo compartido y recibir pruebas puras;
los servidores solo traducen HTTP, permisos y persistencia. La prueba
`tests/test_server_boundaries.py` impide que PostgreSQL vuelva a depender del
servidor SQLite.

## Persistencia

SQLite guarda `centro_operativo.db`. PostgreSQL guarda el estado operativo en el
volumen `postgres_data`; no publica el puerto de la base. Los scripts de prueba
usan el proyecto Compose `librodetrabajo-tests`, su propio volumen y una base
aleatoria por ejecución.

El esquema todavía conserva una fase de bootstrap idempotente dentro de ambos
adaptadores. `schema_migrations` registra las transformaciones incrementales. En
SQLite, los registros históricos reciben un checksum y un cambio posterior de
una definición aplicada detiene el arranque. Las nuevas transformaciones deben
tener una clave nueva; nunca se edita una migración aplicada.

## Seguridad y red

Desarrollo admite HTTP en loopback. Producción exige secretos fuertes y
`PUBLIC_BASE_URL=https://...`; FastAPI debe quedar en `127.0.0.1:8000` detrás de
un proxy TLS privado. Las cookies de sesión son `HttpOnly`, `Secure` y
`SameSite=Strict`. Véase la sección de operación segura de este documento.

## Herramienta local de diseño UI/UX

Desde el 23/09/2026, el proyecto dispone de UI UX Pro Max (UUPM) en
`.claude/skills/ui-ux-pro-max/`. Su punto de entrada es `SKILL.md`; incluye
referencias de diseño, catálogos CSV en `data/` y un buscador Python en
`scripts/search.py`.

UUPM pertenece al entorno de desarrollo. No es un servicio del backend, una
dependencia de FastAPI ni un componente que se ejecute en el navegador. El
Dockerfile actual no copia `.claude/` a la imagen. Los servidores siguen
sirviendo el HTML, CSS y JavaScript de `app/static/`.

El flujo es: solicitud de interfaz → lectura de la skill y consulta local →
selección de reglas aplicables → implementación JSX en `frontend/` → Vite en Docker.
Los agentes de cualquier área que modifiquen una interfaz deben consultar ese
punto de entrada, verificar la pertinencia de sus recomendaciones y preservar
la identidad azul corporativa, los contratos HTTP y los permisos existentes.

Las rutas operativas y de Supervisión se montan desde `frontend/main.jsx`.
`frontend/app-shell.jsx` controla autenticación, navegación, encabezado, tema y
modelos de las vistas. El cambio de módulo conserva los componentes React
montados y no ejecuta el enrutador histórico `app/static/app.js`, que permanece
solo como referencia de compatibilidad. `app/static/index.html` es un punto de
montaje mínimo. Vite integra React 18, PrimeReact 10, PrimeIcons y Tailwind CSS 3
y genera recursos bajo `app/static/frontend/`. El inicio de sesión usa una
pantalla completa React. `legacy_archive/wfm.js` conserva una implementación histórica
utilizada por herramientas de prueba, pero no se carga en el runtime. Tailwind
usa prefijo `tw-`, `important: true` y mantiene Preflight desactivado; sus
utilidades también alcanzan los portales montados en `document.body`.
El Dockerfile compila estos recursos en una etapa Node y copia
solo su salida a la imagen Python final. El archivo histórico no forma parte de la imagen ni de los recursos públicos.

Avisos, Zonas con demora, Tiempos estándar de llegada en Configuración, Auditoría histórica de demoras y Auditoría
general usan páginas PostgreSQL de 50 filas. Sus respuestas incluyen `items`,
`total`, `limit` y `offset`. Horarios devuelve la lista completa del rango
seleccionado: fusiona proyecciones WFM, revisiones publicadas anteriores a la
proyección y registros históricos. Planificación WFM, solicitudes, Programados,
Cotizador y los demás listados de Configuración no se paginan. Los cambios de pestaña
y día muestran inmediatamente la selección y un estado de carga React mientras
se obtiene el contenido.

### Contrato de carga y actualización de las vistas

`frontend/app-shell.jsx` conserva montadas las vistas ya visitadas. Cada carga
inicial o recarga tiene un número de secuencia por vista: una respuesta anterior
no reemplaza a la última. El cierre o cambio de sesión invalida la generación,
aborta las solicitudes pendientes del shell y descarta sus respuestas, errores y
actualizaciones visuales. Las vistas que cargan páginas por su cuenta mantienen
también una secuencia local para descartar respuestas de filtros anteriores.

| Vista | Fuente y filtro principal | Actualización |
| --- | --- | --- |
| Resumen | Estadísticas de demoras, GeoJSON y consulta de tiempo estándar por prestación y zona | Al entrar, al volver a visibilidad, periódicamente y tras cambios de demoras o tiempos estándar |
| Avisos | `/api/notices/page`, filtros y página en el componente | Tras guardar y al cambiar filtros o página; secuencia local |
| Cotizador | Tarifas, cálculo e historial dentro del componente | Al calcular o recuperar una cotización; conserva el borrador local |
| Zonas con demora | `/api/delays` y catálogo geográfico; filtros y página | Tras guardar, al aplicar filtros y con actualización de la vista activa |
| Programados | `/api/transfers` con filtros | Tras sus operaciones y al aplicar filtros |
| Horarios | `/api/schedules`, personas y solicitudes | Al cambiar semana/filtros o solicitudes WFM |
| Configuración → Tiempos estándar de llegada | `/api/arrival-times` y catálogo, página de 50 | Tras guardar, filtros y paginación; Resumen consulta `/api/arrival-times/department` |
| Supervisión y auditorías | Indicadores o páginas filtradas de sus entidades | Al entrar o al volver tras una mutación relacionada |
| Configuración y WFM | Consultas específicas de la pestaña, plan y solicitudes | Tras guardar o cambiar pestaña, día o equipo |

Las mutaciones exitosas emiten `libro:operational-change` con la ruta de la
entidad. El shell marca únicamente las vistas dependientes para refrescarlas al
volver; si Resumen está visible, lo actualiza sin recargar toda la aplicación.
El módulo donde se efectuó la escritura conserva su propio flujo de refresco y
su formulario. Una falla de lectura muestra un error y permite reintentar. Si
la red se corta durante una escritura, el resultado queda **sin confirmar**:
no se repite automáticamente; se consulta el estado actual antes de reintentar.
Todas las solicitudes del shell tienen un límite de 30 segundos en el navegador.
Al vencer, una lectura informa que no terminó y permite reintentar. Una
escritura informa que el resultado es **sin confirmar**: abortar la espera del
navegador no garantiza que PostgreSQL haya cancelado la transacción. La
cancelación al cambiar de sesión tampoco confirma que el servidor canceló
una escritura.

Avisos, Programados, Tiempos de arribo y Demoras usan revisiones para las
ediciones operativas. El formulario envía la revisión que abrió; PostgreSQL
bloquea la fila y acepta la primera transacción sobre esa revisión. La siguiente
recibe HTTP `409`, conserva su borrador y debe revisar la versión vigente antes
de guardar. Las altas de Avisos, Programados y Demoras conservan sus controles
de duplicados; una alta de otro registro no compite por una revisión existente.
Usuarios, roles/permisos, tarifas, peajes, acceso Google, reglas WFM y
requerimientos semanales aplican el mismo control al editar: un `409` exige
recargar los valores actuales antes de volver a guardar.

En Resumen, mapa y tiempos estándar tienen estados de carga y fallo independientes.
Se conserva la última lectura válida con su hora, y una falla nunca se traduce en
«sin demoras» ni en un tiempo de arribo confirmado. Los vencimientos del mapa
se recalculan al alcanzar `review_due_at` sin cerrar la consulta del departamento
ni perder la zona seleccionada. La próxima respuesta del servidor retira
las demoras normalizadas. Resumen no consulta `/api/operational-alerts`.
El intervalo de actualización actual del Resumen es de 60 segundos mientras la
pestaña está visible. Si otras vistas necesitan actualización periódica se
decidirá según su uso; no se presupone un intervalo nuevo en el código.

Para coordinar cambios por módulo, `frontend/app-shell.jsx` es el contrato
compartido de sesión, navegación, carga e invalidación; `frontend/dashboard.jsx`
y `frontend/delay-map-state.js` pertenecen al Resumen; `app/delay_map_stats.py`
y el endpoint de mapa de `app/postgres_server.py` definen el payload
operativo. Integrar primero el contrato del shell, después el payload del
backend y por último la vista y sus pruebas. Si otro módulo necesita cambiar
un archivo compartido, coordinar su interfaz antes de editarlo. Programados,
Horarios, WFM, Cotizador y Configuración mantienen sus responsables de vista
en sus respectivos archivos `frontend/*.jsx`; no se redefinen sus reglas de
negocio desde Resumen.

El shell React separa navegación operativa de Supervisión. Resumen presenta el
mapa de demoras y un panel fijo de consulta por zona y prestación; las métricas
están en Dashboard de Supervisión.
Auditoría de demoras permite consultar el alta, la normalización, sus autores
y el registro de eventos históricos. El Cotizador ordena explícitamente base
de salida, origen y destino, y agrupa kilómetros e importes en el resultado.

### Directiva Global de Diseño UI/UX y Sistema de Componentes

A partir de la infraestructura PrimeReact + Tailwind activa, toda pantalla nueva
o migrada debe cumplir la directiva canónica de [`CLAUDE.md`](CLAUDE.md):

1. Usar exclusivamente componentes nativos de PrimeReact para tablas, listas,
   selectores, diálogos, calendarios, navegación y demás interacción compleja.
2. Estilizar mediante Tailwind con prefijo `tw-` y el aislamiento configurado, o
   mediante presets PrimeReact compatibles con la base Lara Light Blue.
3. Mantener el azul corporativo `#1677ff` / `#2563eb`, fondos
   `tw-bg-gray-50`, superficies `tw-bg-white`, sombras `tw-shadow-sm` y bordes
   `tw-rounded-md`.
4. Mantener densidad B2B: filas de 36 px a 40 px, datos tabulares en 13 px/14 px,
   paddings compactos y jerarquía visible.
5. Reservar `--color-urgente`, `--color-espera` y `--color-ok` para sus estados
   semánticos definidos; el color no puede ser el único indicador.
6. Alojar acciones secundarias de fila en menús kebab (`⋮`) accesibles, evitando
   acumular botones en tablas.

El desarrollo frontend es exclusivamente React/JSX, PrimeReact y Tailwind.
La existencia de archivos históricos no autoriza reutilizarlos ni agregar
parches de layout a `styles.css`, otras hojas globales o `app.js`.
Resolver la composición propia de cada vista en JSX con utilidades y propiedades
nativas o Pass Through (`pt`) de PrimeReact, conservando los contratos HTTP. La
escala transversal del runtime React se mantiene en `frontend/visual-system.css`,
importado por `frontend/main.jsx`: sus tokens y reglas cubren superficies,
controles, tablas, diálogos y paneles portados a `document.body`. No agregar
parches nuevos a las hojas históricas de `app/static/` para estos componentes.

### Sistema visual operativo

`frontend/main.jsx` configura PrimeReact de forma compartida; `frontend/dense-table.jsx`
conserva la tabla paginada densa. `frontend/app-shell.jsx` aporta el encabezado,
la navegación y `data-view`, que permite adaptar la composición sin introducir
estilos arbitrarios en cada pantalla. La escala común es 22 px para el título,
16 px para secciones, 14 px para tarjetas y texto corriente, 13 px para datos y
controles, 12 px para etiquetas y metadatos; controles de 36 px, separación de
12/8 px y tarjetas de 12–16 px. Las filas de tabla empiezan en 36 px y crecen
con el contenido. Menús largos usan un máximo de 264 px, sin altura obligatoria.

| Área | Prioridad de lectura y composición |
| --- | --- |
| Resumen | Mapa junto a la indicación comunicable para GRÚA, ML y SINIESTROS; el detalle queda bajo demanda. |
| Avisos | Tabla y acción de alta, filtros compactos, detalle completo en diálogo. |
| Zonas con demora | Prestación, ubicación, vigencia e instrucción comunicable. |
| Programados | Fecha/hora, tarea, estado, prestador y responsable. |
| Cotizador | Datos de entrada y resultado juntos; precio y desglose visibles. |
| Horarios | Matriz semanal de Equipo y tarjetas propias para Mis horarios. |
| WFM | Navegación y publicación estratégicas sin cambiar reglas de planificación. |
| Configuración | Formularios y catálogos, incluidos tiempos estándar. |
| Auditorías | Filtros, fecha, actor y cambios en tablas consultables. |

El ejecutor `tools/browser_interaction/run.cjs` monta el bundle React real con
respuestas sintéticas; valida el marco visual a 1920, 1536 y 1280 px, el tema
oscuro, ampliación de la vista, tamaño de menú y flujos de interacción. Las
capturas opcionales se habilitan mediante `VISUAL_OUTPUT`; no sustituyen una
revisión manual de cada dato y permiso en un entorno de pruebas.

Telefonistas requieren alta densidad, lectura rápida sin scroll horizontal y
acciones directas. Planificadores necesitan visión estratégica y grillas
precisas. Aplicar `tw-text-[13px]` o `tw-text-sm`, `tw-p-4`, `tw-gap-3`,
DataTable con `size="small"` y `stripedRows`; textos largos con
`tw-whitespace-normal tw-break-words`. Reservar mínimos para Fecha, Antigüedad
y Tarea y mantener fechas/horas completas con `tw-whitespace-nowrap`.
Dropdown y Calendar deben declarar `appendTo={document.body}`. Calendar conserva
su estructura flex y `showIcon`; los modales no deben recortar sus selectores.
Las botoneras usan flex con wrap y ancho completo, sin posiciones absolutas,
márgenes negativos ni anchos rígidos. Estas reglas se mantienen idénticas en
`AGENTS.md` y `CLAUDE.md` y prevalecen sobre ejemplos históricos de otras guías.

La presencia de la carpeta no garantiza que una conversación haya leído la
skill. El protocolo y los comandos están en
[`tools/ui_ux_guidance/README.md`](tools/ui_ux_guidance/README.md); las instrucciones
iniciales del apartado 11 están en
[`tools/ui_ux_guidance/PROMPT_11.md`](tools/ui_ux_guidance/PROMPT_11.md).
Las reglas del usuario y de `AGENTS.md` prevalecen sobre recomendaciones UUPM.
Esta incorporación documental no establece una paleta nueva ni certifica la
accesibilidad de las pantallas existentes.

## Decisiones de compatibilidad

- El modo SQLite continúa disponible y no se usa en paralelo con PostgreSQL.
- Las migraciones son aditivas y las interfaces HTTP existentes se conservan.
- Los datos WFM locales son entradas operativas excluidas de Git; su contrato se
  documenta en la sección de datos locales de este documento.
- `CHANGELOG.md` es la fuente del historial visible y `APP_VERSION`, en
  `app/application.py`, identifica la entrega actual.

## Operación segura, datos locales y respaldos

- `centro_operativo.db` es el origen histórico protegido: no sobrescribirlo ni
  eliminarlo. No alternar operación entre SQLite y PostgreSQL.
- `data/` contiene entradas operativas excluidas de Git. WFM puede importar
  `data/wfm/telefonistas-horarios-semanales.json` y excepciones
  `data/wfm/telefonistas-horarios-AAAA-Www.json`. No son necesarias para leer
  registros ya persistidos; una clonación no incluye esas fuentes.
- Trasladar datos solo por canales autorizados: SQLite con sus respaldos;
  PostgreSQL mediante un dump y su SHA-256, nunca copiando el volumen interno.
  `.env` se administra por separado y nunca se imprime ni se versiona.
- Producción usa `APP_ENV=production`, secretos fuertes, HTTPS y hosts/orígenes
  explícitos. PostgreSQL no publica puertos. El proxy TLS autorizado apunta a
  `127.0.0.1:8000`; el proyecto no modifica el firewall.
- Las sesiones se almacenan como hashes; el navegador usa cookies HttpOnly,
  Secure y SameSite=Strict, sin tokens en Web Storage. Operaciones modificadoras
  requieren CSRF. Hay vencimiento absoluto y por inactividad; cambiar contraseña
  o desactivar un usuario revoca sesiones.
- `ADMIN_PASSWORD` inicializa una base vacía; no cambia usuarios existentes.
  Modificar `POSTGRES_PASSWORD` tampoco rota un rol ya creado. Cualquier rotación
  requiere coordinación y respaldo, sin exponer valores en comandos o registros.
- Ante pérdida de un equipo, desactivar usuarios afectados, cambiar contraseñas,
  revisar auditoría y coordinar la rotación de secretos que se hayan expuesto.
- El servicio `backup` genera copias cada 15 minutos por defecto. Las copias en
  el mismo disco no cubren pérdida del equipo. Retención y copia corporativa
  externa requieren política aprobada; no hay envío automático a la nube.
- Restaurar siempre en una base/volumen nuevo y validar antes de habilitar usuarios.
  No ejecutar `docker compose down -v` sobre la operación. Las herramientas
  `tools/postgres_backup/`, `tools/postgres_restore_test/` y
  `tools/portability_check/` conservan sus procedimientos y requisitos.

Para una entrega de producción ya validada:

```powershell
docker compose -f compose.yaml -f compose.production.yaml up -d --no-build --wait
docker compose ps
```

Comprobar `/health` y HTTPS desde el acceso autorizado. No aplicar una migración
nuevamente por cambiar de computadora ni restaurar pruebas sobre la base activa.

## Contratos operativos que la interfaz debe preservar

- Métricas: una instantánea `as_of`, fechas de negocio en `America/Montevideo`,
  intervalos desde el inicio de `date_from` hasta el inicio del día siguiente a
  `date_to`. Los totales no dependen de la página de la tabla; denominador cero
  se presenta como «Sin datos». Distinguir métricas actuales del período histórico.
- Avisos abiertos: `PENDIENTE`, `EN_GESTION`, `ESPERANDO_RESPUESTA`; terminales:
  `RESUELTO`, `CANCELADO`. «Todos los estados» incluye En gestión. Enter aplica
  los mismos filtros que el botón. Guardar/asignar/cerrar refresca datos sin
  recargar la página ni perder filtros. Conservar permisos y detección de duplicados.
- Demoras: vigencia verificada requiere `VIGENTE` y revisión futura. La revisión
  vencida no representa una demora confirmada. Respetar la fecha de expiración o
  el plazo de revisión del backend; mapa y listados usan la misma interpretación.
- Programados: conservar transición de estados y equivalencias históricas
  `PENDIENTE` → `SIN_ASIGNAR`, `CONFIRMADO` → `ASIGNADO`,
  `COMPLETADO` → `FINALIZADO`. La asignación requiere los datos del prestador;
  cierre y cancelación conservan su motivo y auditoría.
- Horarios: respetar fechas locales y semanas ISO, mostrar historial publicado
  sin incluir borradores. Cambiar semana/filtros mantiene el montaje React.
- Cotizador: tarifas y validación provienen del backend; no copiar importes
  históricos a JSX. Preservar tramos, kilómetros excedentes, peajes manuales y
  automáticos, límites, redondeos y deduplicación establecidos en `app/quotes.py`
  y `app/tolls.py`. Moneda con formato `es-UY`; Leaflet conserva limpieza al
  desmontar, proxy de tiles y zoom.
- Exportaciones: mismos filtros que la vista, todos los registros coincidentes,
  CSV UTF-8 con BOM y separador punto y coma; conservar protección de fórmulas
  y autorización/auditoría del backend.
- Auditoría: actor, entidad, fecha, antes/después y correlación sin secretos;
  no modificar eventos históricos desde la interfaz.

## Desarrollo y comprobación

Las entregas de servidor conservan el perfil `sistemas-20260925`, incorporado
desde el ZIP revisado por Sistemas: `APP_PORT` configurable con 8000 interno,
identidad Compose estable, logs json-file limitados a 10 MB × 3 por servicio,
init y no-new-privileges para app, 60 s de margen inicial de salud y espera de
arranque de 240 s. El empaquetador verifica su presencia antes de generar el ZIP.
Las plantillas no sustituyen el `.env` ni el nombre de proyecto del servidor.
Procedimiento y comprobación de puertos en `tools/deployment/README.md`.
El ZIP identifica la revisión de referencia y el contenido efectivo mediante
hashes; se detiene si falta inventariar un módulo nuevo de `app/` o `frontend/`.
La validación de Compose contempla también el worker opcional. Las pruebas
PostgreSQL usan proyectos temporales independientes, aptos para ejecuciones
simultáneas sin detener la base manual de pruebas.

Revisar cambios existentes antes de editar. Frontend: únicamente Vite y sintaxis
JS/JSX en Docker; comandos en `tools/frontend_build/README.md`. Backend: pruebas
acordes al dominio y adaptador, con bases aisladas según `tools/test_all/` y
`tools/postgres_test_db/`. No modificar checksums de migraciones ya aplicadas.

La documentación central es README, ARCHITECTURE y las instrucciones idénticas
AGENTS/CLAUDE. Los manuales en `tools/` y `.claude/skills/` se conservan junto a
sus herramientas. `CHANGELOG.md` permanece porque `app/releases.py` lo consume
para el historial visible. Las notas de entregas y auditorías antiguas se
consultan en Git, no se usan como reglas actuales.
