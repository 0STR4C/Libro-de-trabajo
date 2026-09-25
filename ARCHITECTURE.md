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
`SameSite=Strict`. Consulte `SECURITY.md` y `DEPLOY_LOCAL_NETWORK.md`.

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
selección de reglas aplicables → implementación en `app/static/` → validación.
Los agentes de cualquier área que modifiquen una interfaz deben consultar ese
punto de entrada, verificar la pertinencia de sus recomendaciones y preservar
la identidad azul/turquesa, los contratos HTTP y los permisos existentes.

Las diez rutas operativas montan vistas React desde `frontend/main.jsx`. Vite
integra React 18, PrimeReact 10, PrimeIcons y Tailwind CSS 3 y genera recursos
bajo `app/static/frontend/`. El enrutador, la navegación lateral, el encabezado
y el selector de tema aún viven en `app/static/app.js` e `index.html`; por eso
la aplicación completa todavía no es 100 % React. El inicio de sesión ya usa
un `Dialog` React. `app/static/wfm.js` conserva una implementación histórica
utilizada por herramientas de prueba, pero no se carga en el runtime. Tailwind
usa prefijo `tw-`, se limita a `#prime-react-root` y mantiene Preflight
desactivado. El Dockerfile compila estos recursos en una etapa Node y copia
solo su salida a la imagen Python final. Véase [auditoría de migración](MIGRATION_AUDIT.md).

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

Mientras exista el shell heredado, conservar el prefijo `tw-`, el selector
`#prime-react-root` y Preflight desactivado. No mezclar parcialmente los sistemas
de componentes en un mismo flujo sin una excepción documentada y validada.

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
  documenta en `DATA_MANIFEST.md`.
- `CHANGELOG.md` es la fuente del historial visible y `APP_VERSION`, en
  `app/application.py`, identifica la entrega actual.
