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

- Rutas de React: ingreso directo, continuidad después del login, refresco,
  Atrás/Adelante, enlace a otra pestaña, semana de Horarios, historial del
  Cotizador, planificación, subsección de Configuración, permiso denegado y
  ruta inexistente. Los parámetros sensibles se descartan de la dirección.

- Login React con foco inicial, nombres de usuario y contraseña, navegación a Avisos y anuncio de carga.
- Filtros por Enter; dos respuestas fuera de orden; resultado vacío; detalle largo en diálogo.
- Menú de fila abierto por teclado y Escape; asociación visible y accesible de campos; validación sin POST.
- Error HTTP 422 con aviso y reintento, doble envío durante un POST demorado, guardado y refresco.
- Conflicto HTTP 409 que conserva el borrador y bloquea Guardar hasta elegir una resolución.
- Foco inicial y retorno con Escape en los diálogos de aviso y salida; cancelación, confirmación pendiente y logout.
- Cambio de sesión por respuesta 401; fallo de carga anunciado y botón Reintentar.
- Escala visual del React real a 1920×1080, 1536×864 y 1280×720; ancho de página, altura mínima de controles, tipografía de tabla, altura máxima de menú, tema oscuro y ampliación al 125 %.
- Montaje y ausencia de desborde de Resumen, Avisos, Cotizador, Demoras, Programados, Horarios, Mis solicitudes, Dashboard de Supervisión, WFM, auditorías y Configuración con respuestas vacías sintéticas a 1920 y 1280 px.
- Resumen con el GeoJSON real a 1920 px y panel debajo del mapa a 1024 px; zona buscable, indicaciones por prestación, afectación de `TODAS`, errores y normalización con respuestas API sintéticas. Comprueba que Resumen no consulta alertas operativas.
- Avisos a 1920 px: calendario en español, siete columnas contenidas en el popup, resaltado alineado de la vista seleccionada y anillo del estado solo mientras su menú está abierto (conservando el indicador de foco de teclado).
- En el recorrido transversal se abren el calendario y el formulario de Demoras, el modal de Programados, el modo manual del Cotizador y la vista Mis horarios; se verifica Escape y el nombre accesible del selector de prestación.

Para guardar capturas sintéticas, montá una carpeta del proyecto como `/visual-output`
y pasá `-e VISUAL_OUTPUT=/visual-output` a `docker run`. El ejecutor crea
`resumen-mapa-real-1920.png`, `resumen-consulta-1920.png`, `avisos-1920.png`, `avisos-oscuro-1280.png` y una captura de cada módulo
recorrido a 1920 px en esa carpeta. Las capturas y las
pruebas usan un usuario y avisos inventados.

Las respuestas son sintéticas: esta suite prueba el montaje, los eventos y la interfaz del React real, pero no certifica reglas ni persistencia del backend. Las rutas API no previstas, excepciones de página y fallas de aserción hacen fallar la corrida.
