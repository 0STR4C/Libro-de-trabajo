# Arquitectura técnica

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

Las diez rutas operativas montan vistas React desde `frontend/main.jsx`. Vite
integra React 18, PrimeReact 10, PrimeIcons y Tailwind CSS 3 y genera recursos
bajo `app/static/frontend/`. El enrutador, la navegación lateral, el encabezado
y el selector de tema aún viven en `app/static/app.js` e `index.html`; por eso
la aplicación completa todavía no es 100 % React. El inicio de sesión ya usa
una pantalla completa React. `legacy_archive/wfm.js` conserva una implementación histórica
utilizada por herramientas de prueba, pero no se carga en el runtime. Tailwind
usa prefijo `tw-`, `important: true` y mantiene Preflight desactivado; sus
utilidades también alcanzan los portales montados en `document.body`.
El Dockerfile compila estos recursos en una etapa Node y copia
solo su salida a la imagen Python final. El archivo histórico no forma parte de la imagen ni de los recursos públicos.

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
Resolver el estilo del componente en JSX con utilidades y propiedades nativas
o Pass Through (`pt`) de PrimeReact, conservando los contratos HTTP.

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

Revisar cambios existentes antes de editar. Frontend: únicamente Vite y sintaxis
JS/JSX en Docker; comandos en `tools/frontend_build/README.md`. Backend: pruebas
acordes al dominio y adaptador, con bases aisladas según `tools/test_all/` y
`tools/postgres_test_db/`. No modificar checksums de migraciones ya aplicadas.

La documentación central es README, ARCHITECTURE y las instrucciones idénticas
AGENTS/CLAUDE. Los manuales en `tools/` y `.claude/skills/` se conservan junto a
sus herramientas. `CHANGELOG.md` permanece porque `app/releases.py` lo consume
para el historial visible. Las notas de entregas y auditorías antiguas se
consultan en Git, no se usan como reglas actuales.