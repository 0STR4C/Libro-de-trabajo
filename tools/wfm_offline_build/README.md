# Actualización local sin descargar dependencias

`ui_smoke.cjs` conserva pruebas históricas con `legacy_archive/wfm.js` y
`legacy_archive/wfm.css`. Esos recursos no se publican ni acreditan la paridad
del módulo React vigente (`frontend/wfm.jsx`). Los scripts y contratos se
conservan para reproducción, no como instrucciones para construir UI nueva.
Las instrucciones actuales exigen runtimes dentro de Docker; los comandos Node
y pnpm documentados abajo son referencias del harness histórico, no autorización
para ejecutarlos en el host. La validación UI actual usa únicamente Vite y
sintaxis JS/JSX según `tools/frontend_build/README.md`.

Propósito: reconstruir una revisión del código y su bundle Vite sobre las imágenes
locales existentes. Requiere Docker Desktop, `librodetrabajo-app:latest` y
`librodetrabajo-frontend-check:latest`. No instala paquetes ni descarga archivos.
Las versiones de las imágenes deben coincidir con `requirements.txt` y
`package-lock.json`; no usar este método si cambian dependencias.

Desde la raíz del proyecto:

```powershell
docker build --network=none -f tools/wfm_offline_build/Dockerfile -t centro-wfm-candidate:latest .
powershell -ExecutionPolicy Bypass -File tools/postgres_security_test/run.ps1 -ImageName centro-wfm-candidate:latest
```

Entrada: `app/`, `frontend/`, configuración Vite, `CHANGELOG.md` e imágenes locales. Salida: imagen candidata. No modifica
bases, archivos originales ni contenedores activos. El segundo comando crea
contenedores efímeros de prueba sin volumen operativo. No publica el resultado.

## Prueba de interfaz sin datos reales

Requiere Node, Playwright 1.62.1 y Edge. Playwright se instala localmente en
esta herramienta, con la versión fijada en `package.json` y `pnpm-lock.yaml`.
No necesita descargar Chromium ni utiliza el perfil personal del navegador.

Instalación reproducible desde la raíz del proyecto:

```powershell
pnpm --dir tools/wfm_offline_build install --frozen-lockfile
```

Ejecución desde la raíz del proyecto:

```powershell
node tools/wfm_offline_build/ui_smoke.cjs
node tools/wfm_offline_build/dashboard_smoke.cjs
node tools/wfm_offline_build/notice_smoke.cjs
```

Para conservar capturas visuales con los mismos datos sintéticos:

```powershell
$env:UX_SCREENSHOT_DIR = ".\artifacts\ui-ux"
node tools/wfm_offline_build/ui_smoke.cjs
node tools/wfm_offline_build/dashboard_smoke.cjs
node tools/wfm_offline_build/notice_smoke.cjs
Remove-Item Env:UX_SCREENSHOT_DIR
```

La carpeta indicada recibe `novedades-escritorio.png`, `novedades-movil.png`,
`formulario-movil.png`, `resumen-escritorio.png`,
`resumen-oscuro.png`, `resumen-sidebar-minimizado.png`, `resumen-movil.png`,
`arribos-escritorio.png`, `arribos-movil.png`, `avisos-nuevo-modal.png`,
`avisos-tabla-escritorio.png`, `avisos-tabla-oscuro.png` y
`avisos-tabla-movil.png`. La herramienta no sobrescribe datos de la aplicación;
solo esos archivos de salida si ya existen en el destino elegido.

Comprueba alta, cruce de medianoche, tijera, merma sobre la cobertura, punto de
agarre, tamaño y opacidad de la vista previa, alta rápida, resize y edición por
doble clic de excepciones, menú contextual, publicación diaria y semanal, vista
individual, portal de solicitudes y Horarios de solo lectura conectado a la
fuente publicada con búsqueda en vivo y mediante Enter.
También renderiza el historial de Novedades con versiones sintéticas, comprueba
su expansión inicial y verifica que no desborde una pantalla móvil de 390 px.
En ese mismo viewport comprueba la apertura y cierre de la navegación, el
significado de las columnas en tablas adaptables y la asociación entre etiquetas
y campos obligatorios dentro de un modal.
`dashboard_smoke.cjs` comprueba el montaje PrimeReact, las clases Tailwind, los
tres modos de tema y la jerarquía Mapa y demoras → Avisos operativos →
Programados con datos sintéticos. También valida el orden Supervisión →
Configuración, el chevron a la derecha y su ocultamiento al minimizar, la
ausencia de solapamientos y el ancho móvil. La misma prueba verifica que las
tarjetas, badges y acciones de Tiempos de arribo no desborden sus contenedores.
`notice_smoke.cjs` comprueba las tarjetas y `DataTable` PrimeReact, filas de
36–40 px en escritorio, tema oscuro, el modal de alta, la autoasignación, los
permisos del menú contextual, el menú de estado debajo de su disparador y la
adaptación móvil de Avisos. También valida el Header sin subtítulo ni indicador
de sistema, el perfil desplegable y la salida con color semántico.
La API se simula y toda petición del navegador se bloquea. Solo crea el perfil
temporal de Edge que Playwright gestiona; no modifica archivos ni datos operativos.
