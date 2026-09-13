# Actualización local sin descargar dependencias

Propósito: probar una revisión del código sobre la imagen local existente.
Requiere Docker Desktop y la imagen `librodetrabajo-app:latest` ya disponible.
No instala paquetes. Las versiones siguen siendo las de esa imagen y deben
coincidir con `requirements.txt`; no usar este método si cambian dependencias.

Desde la raíz del proyecto:

```powershell
docker build --network=none -f tools/wfm_offline_build/Dockerfile -t centro-wfm-candidate:latest .
powershell -ExecutionPolicy Bypass -File tools/postgres_security_test/run.ps1 -ImageName centro-wfm-candidate:latest
```

Entrada: `app/`, `CHANGELOG.md` e imagen local existente. Salida: imagen candidata. No modifica
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
```

Para conservar capturas visuales con los mismos datos sintéticos:

```powershell
$env:UX_SCREENSHOT_DIR = ".\artifacts\ui-ux"
node tools/wfm_offline_build/ui_smoke.cjs
Remove-Item Env:UX_SCREENSHOT_DIR
```

La carpeta indicada recibe `novedades-escritorio.png`, `novedades-movil.png` y
`formulario-movil.png`. La herramienta no sobrescribe datos de la aplicación;
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
La API se simula y toda petición del navegador se bloquea. Solo crea el perfil
temporal de Edge que Playwright gestiona; no modifica archivos ni datos operativos.
