# Pruebas de interacción del runtime React

Este ejecutor abre el `index.html` y el bundle Vite compilado desde `frontend/` en Chromium. Sirve los archivos reales de `app/static/`; solo reemplaza las respuestas HTTP de `/api/*` y el GeoJSON por datos sintéticos. No utiliza la base operativa ni credenciales reales.

## Inventario previo

| Prueba existente | Qué monta | Alcance respecto al React actual |
| --- | --- | --- |
| `tools/wfm_offline_build/ui_smoke.cjs` | HTML y endpoints simulados, más código de WFM histórico | No monta el shell React actual. |
| `tools/wfm_offline_build/dashboard_smoke.cjs` y `notice_smoke.cjs` | HTML modificado, `app.js` heredado y montaje manual | No recorren la entrada actual `frontend/main.jsx` → `AppShell`. |
| `tools/branding/test-branding.cjs` | Servidor local en `127.0.0.1:8000` | Puede observar el React servido, pero depende de una instancia externa y solo revisa marca. |
| Pruebas Python de layout en `tests/` | Archivos fuente y HTML | Son comprobaciones estáticas, sin navegador ni eventos React. |

## Ejecución reproducible

Desde la raíz del proyecto:

```powershell
docker build -f tools/browser_interaction/Dockerfile -t libro-browser-interaction:local .
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges libro-browser-interaction:local
```

La primera construcción descarga `node:22-alpine`, `mcr.microsoft.com/playwright:v1.62.1-noble` y dependencias fijadas en ambos lockfiles, si no están en caché. La imagen compila Vite durante el build y ejecuta Chromium dentro de Docker. El proceso devuelve código `0` si todas las pruebas pasan y código distinto de `0` con el nombre y la causa de cada falla. Infraestructura puede integrar esos dos comandos en CI. No requiere Compose ni expone puertos al host.

Entradas: `frontend/`, `app/static/`, configuraciones Vite/Tailwind, `package-lock.json` y los archivos de este directorio. Salidas: imagen Docker local y resultado de pruebas por stdout; el ejecutor no modifica archivos del proyecto. El servidor HTTP de prueba escucha solo en `127.0.0.1` dentro del contenedor y se cierra al terminar.

## Escenarios cubiertos

- Login React con foco inicial, nombres de usuario y contraseña, navegación a Avisos y anuncio de carga.
- Filtros por Enter; dos respuestas fuera de orden; resultado vacío; detalle largo en diálogo.
- Menú de fila abierto por teclado y Escape; asociación visible y accesible de campos; validación sin POST.
- Error HTTP 422 con aviso y reintento, doble envío durante un POST demorado, guardado y refresco.
- Conflicto HTTP 409 que conserva el borrador y bloquea Guardar hasta elegir una resolución.
- Foco inicial y retorno con Escape en los diálogos de aviso y salida; cancelación, confirmación pendiente y logout.
- Cambio de sesión por respuesta 401; fallo de carga anunciado y botón Reintentar.

Las respuestas son sintéticas: esta suite prueba el montaje, los eventos y la interfaz del React real, pero no certifica reglas ni persistencia del backend. Las rutas API no previstas, excepciones de página y fallas de aserción hacen fallar la corrida.
