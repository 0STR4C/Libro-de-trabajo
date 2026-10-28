# Guía de trabajo: Libro de trabajo

## Avance y autonomía

- Completá las tareas autorizadas de principio a fin. Elegí la vía técnica que mejor resuelva el problema y explicá los obstáculos reales; estas pautas no deben provocar rodeos ni impedir una solución correcta.
- Antes de editar, revisá el estado de Git y conservá los cambios existentes. Limitá cada cambio y cada commit a los archivos de la tarea.
- Podés usar el host o Docker para ejecutar herramientas, compilar y probar, según convenga. Preferí Docker cuando reproduzca mejor el entorno de la aplicación; no hagas intentos de fallback innecesarios.
- Podés usar Internet y descargar dependencias, documentación e imágenes necesarias para implementar, compilar y verificar tareas del proyecto, incluido el Dockerfile habitual. No hace falta pedir autorización adicional por estas operaciones rutinarias. Mantené las versiones y el origen de las dependencias bajo control y evitá descargar material innecesario.
- Instalá dependencias del proyecto cuando hagan falta. Los cambios globales del sistema operativo o de su seguridad requieren una solicitud específica.
- Usá pruebas proporcionales al cambio. Para UI, compilá con Vite y verificá el comportamiento afectado; ejecutá también pruebas de backend o integración cuando aporten evidencia útil. Investigá y corregí los fallos antes de concluir.
- Si cambiás código de la aplicación, reconstruí con Docker y verificá la salud de los servicios afectados. Usá la construcción normal cuando sea viable; la ruta offline es una alternativa, no una obligación. No sustituyas una imagen reconstruida por archivos copiados temporalmente a un contenedor.

## Seguridad y conservación

- No borres ni alteres datos importantes, archivos fuera del proyecto, configuraciones del sistema o recursos de otras personas sin autorización específica. Para acciones destructivas, identificá el recurso y conservá una vía de recuperación.
- No leas ni difundas secretos o datos privados ajenos a la tarea. Las descargas de dependencias no autorizan enviar datos del proyecto a servicios externos.
- No publiques, envíes mensajes, hagas push ni despliegues en sistemas remotos salvo que la tarea lo autorice. Las acciones locales y reversibles necesarias para completar una tarea autorizada pueden realizarse sin pedir permiso adicional.
- Informá al terminar los cambios, las comprobaciones, los resultados y cualquier limitación real.

## Interfaz

### Demoras y Avisos

- Avisos registra comunicaciones que una persona deja al equipo sobre una llamada, tarea, servicio o caso. Telefonistas y Planificadores pueden aportar información para un eventual rellamado; no es una bandeja de alertas automáticas.
- Los avisos históricos generados por revisión de demoras se retiran administrativamente según su vínculo de origen, conservando registro, estado e historial. El retiro no equivale a una resolución humana y no participa en la operación de Avisos.
- La consulta de llegada del Resumen usa exclusivamente Tiempos estándar y Zonas con demora. Avisos se consulta en su propia pestaña y no aporta tiempos, ámbitos geográficos ni alertas al mapa.
- Zonas con demora registra afectaciones temporales por prestación y ubicación. Su revisión, vencimiento, verificación y normalización permanecen en Demoras y su historial; nunca crean ni actualizan registros de Avisos.
- En Resumen, una demora vigente aplicable reemplaza la indicación del tiempo estándar para esa prestación y ubicación, incluso si requiere revisión. `TODAS` alcanza todas las prestaciones; una demora específica no afecta otras. Una consulta fallida no equivale a ausencia de demoras.
- Conservá literalmente las indicaciones operativas: no confirmar tiempos, margen, máximo, intervalo, texto libre y no generar servicio son significados distintos. No sumes márgenes al estándar, no reduzcas intervalos a un número ni deduzcas «No generar servicio» de «No confirmar tiempos».
- Si varias demoras vigentes se superponen, mostralas y pedí revisión a Planificación sin confirmar un tiempo; no elijas una por fecha. Al normalizar, vuelve a estar disponible la consulta del estándar y queda el historial de la excepción.

- Mantené la experiencia B2B de alta densidad y la pila existente de React, PrimeReact y Tailwind con prefijo `tw-`. Respetá los componentes, tokens y patrones actuales; adaptalos cuando la tarea requiera una mejora concreta.
- Conservá lectura rápida, tablas compactas, texto legible sin superposiciones y páginas sin desbordamiento horizontal. Las grillas temporales pueden usar desplazamiento interno. Usá paginación de 50 filas cuando corresponda.
- Aplicá las preferencias visuales vigentes: sidebar azul marino `#0f172a`, acción primaria azul `#1677ff`/`#2563eb`, estados semánticos rojo/ámbar/verde y selector de tema visible. Los títulos principales se mantienen limpios, sin subtítulos innecesarios.
- En componentes nuevos, preferí estilos locales con utilidades Tailwind, `DataTable` compactas y portales de PrimeReact para paneles flotantes. Ajustá el patrón si mejora accesibilidad o evita fallos de layout.

### Escala visual compartida

- `frontend/visual-system.css`, importado por `frontend/main.jsx`, concentra los tokens de tipografía, espaciado, superficies, controles y paneles flotantes del runtime React. Es la única capa transversal nueva para estos patrones; las vistas conservan su composición operativa en JSX con `tw-`.
- La escala de escritorio es: título de página 22 px; título de sección 16 px; tarjeta y texto corriente 14 px; tabla/control 13 px; etiqueta y metadato al menos 12 px. Control 36 px, separación ordinaria 12 px, elementos relacionados 8 px, tarjeta 12–16 px. No reduzcas fuentes para ocultar desbordes.
- Usá `PrimeReactProvider` de `frontend/main.jsx` para las propiedades y el Pass Through comunes de Card, Button, InputText, Dropdown, Dialog, Menu y DataTable. Ajustá menús largos a un máximo de 264 px con scroll interno y búsqueda cuando la lista lo justifique; conservá `appendTo={document.body}`.
- La tabla operativa permite crecer a filas de varias líneas. Priorizá su información y evitá scroll horizontal de toda la página; una matriz semanal puede desplazar su propia grilla. Los diálogos breves usan 400–480 px, formularios habituales 560–640 px y consultas complejas el espacio que necesiten.
- Comprobá la escala en el navegador con el runtime React y datos sintéticos: `tools/browser_interaction/` cubre 1920, 1536 y 1280 px, modo oscuro, ampliación, menús y flujos principales. No interpretes esa cobertura como certificación de todas las vistas o del backend.

## Empaquetado para servidor

- Para un ZIP de servidor usá `tools/deployment/package_server.py` y su guía. Conservá el perfil de Sistemas `sistemas-20260925`: `APP_PORT` configurable en ambos Compose (8000 interno), identidad estable del proyecto, logs `json-file` de 10 MB × 3 por servicio, `init` y `no-new-privileges` para app, margen inicial de salud de 60 s y espera de arranque de 240 s.
- La plantilla incluye `COMPOSE_PROJECT_NAME` y `BACKUP_MAX_AGE_SECONDS`. Validá la mezcla Compose con valores sintéticos y puerto alternativo, sin reiniciar la operación local. No incluyas secretos, datos ni backups en el ZIP ni reemplaces el `.env` del servidor.
- Preservá el nombre Compose y los volúmenes de una instalación existente. Generá nuevamente manifiesto y checksum para cada ZIP.

`AGENTS.md` y `CLAUDE.md` deben tener contenido idéntico. Las instrucciones explícitas del usuario para una tarea prevalecen sobre estas preferencias.

Las rutas, títulos y permisos de navegación se definen en `frontend/routes.js`; al añadir una sección, actualizá su ruta y verificá el acceso directo, el refresco y el historial del navegador. Las reglas y parámetros admitidos se documentan en `docs/NAVEGACION_URL.md`.
