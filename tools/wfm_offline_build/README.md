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

Entrada: `app/` e imagen local existente. Salida: imagen candidata. No modifica
bases, archivos originales ni contenedores activos. El segundo comando crea
contenedores efímeros de prueba sin volumen operativo. No publica el resultado.

## Prueba de interfaz sin datos reales

Requiere Node, Playwright 1.62.1 (disponible en el runtime de trabajo) y Edge.
No necesita descargar Chromium ni utiliza el perfil personal del navegador.
Si Playwright no está disponible, instalarlo localmente requiere autorización;
las dependencias de prueba se declaran en `package.json`.
Ejecutar **desde la raíz del proyecto**:

```powershell
node tools/wfm_offline_build/ui_smoke.cjs
```

Puede requerir `NODE_PATH` apuntando al directorio de paquetes del runtime.
Comprueba alta, cruce de medianoche, tijera, merma sobre la cobertura, punto de
agarre y opacidad del arrastre, menú contextual, publicación diaria y semanal,
vista individual, portal de solicitudes y Horarios de solo lectura con búsqueda
en vivo y mediante Enter.
La API se simula y toda petición del navegador se bloquea. Solo crea el perfil
temporal de Edge que Playwright gestiona; no modifica archivos ni datos operativos.
