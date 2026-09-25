# Desarrollo y validación

## Requisitos

- Docker Desktop con Compose v2.
- PowerShell 5.1 o posterior.
- Node.js para validar JavaScript.
- Imágenes locales `librodetrabajo-app:latest` y `postgres:16-alpine`.

No se requieren credenciales operativas ni acceso a Internet para las pruebas.

## Flujo de cambio

1. Revisar `git status` y preservar cambios existentes.
2. Crear la regla en el módulo de dominio compartido.
3. Mantener en cada servidor únicamente la consulta o traducción propia de su
   base de datos.
4. Agregar una prueba del comportamiento y, si aplica, una prueba de paridad.
5. Ejecutar desde la raíz:

   ```powershell
   & .\tools\test_all\run.ps1
   ```

Ese comando ejecuta la suite general, valida JavaScript, ejecuta la prueba UI si
Playwright está disponible y siempre llama a
`tools/postgres_test_db/run.ps1`. La base PostgreSQL operativa no participa.

## Desarrollo de interfaz con UI UX Pro Max

Antes de diseñar, modificar o revisar una interfaz, leer `CLAUDE.md`,
`.claude/skills/ui-ux-pro-max/SKILL.md`, `UI_UX_PLAN.md` y el código de la pantalla.
El flujo completo y ejemplos reutilizables están en
[`tools/ui_ux_guidance/README.md`](tools/ui_ux_guidance/README.md).

- Usar una consulta local `--domain` para un problema concreto y
  `--design-system` para una página nueva o una dirección visual global.
- Las pantallas actuales usan HTML, CSS y JavaScript directo. La infraestructura
  de migración en `frontend/` incorpora React, PrimeReact y Tailwind mediante
  Vite, pero no convierte por sí sola las pantallas heredadas. Consultar reglas
  independientes del stack para esas pantallas y reglas React solo para los
  componentes efectivamente migrados. No asumir Next.js.
- Aplicar primero accesibilidad, interacción y legibilidad. Reutilizar los
  estilos y componentes existentes; contrastar las recomendaciones con las
  necesidades de una herramienta operativa antes de implementarlas.
- Si existe `design-system/<project-slug>/MASTER.md`, leerlo junto con las
  excepciones de la página. Generar propuestas inicialmente sin `--persist`;
  persistir únicamente decisiones verificadas dentro del proyecto, indicando
  `--output-dir`. No usar `--force` sin autorización explícita.
- Las consultas usan descripciones genéricas, sin datos operativos o personales.
  Una recomendación de fuente, iconos o animación no autoriza descargas ni nuevas
  dependencias. Si el buscador no puede ejecutarse, declararlo y utilizar las
  referencias locales, sin atribuirles resultados de una búsqueda.

El apartado 11 mantiene la coherencia visual compartida. Las demás áreas aplican
el mismo protocolo cuando sus cambios afectan pantallas. Antes de editar CSS o
JavaScript compartidos, revisar los cambios existentes y delimitar el alcance;
las conversaciones independientes no sustituyen la coordinación de archivos.

Toda implementación conserva la validación general y la suite PostgreSQL aislada
obligatorias. Los cambios exclusivamente documentales requieren verificar rutas,
enlaces, comandos y diferencias, sin reconstruir la aplicación ni cambiar su
versión por incorporar estas instrucciones.

La instalación y compilación frontend se documentan en
[`tools/frontend_build/README.md`](tools/frontend_build/README.md). Usar `npm ci`
para reproducir `package-lock.json` y `npm run build:frontend` para generar los
recursos. No cargar la salida en una pantalla heredada hasta definir el contenedor
y el punto de montaje de esa migración.

## Migraciones

Los cambios de esquema deben ser compatibles con una base existente, tener una
clave única y ser idempotentes. No cambie el contenido asociado a una clave ya
registrada: el checksum existe para detectar esa situación. Valide tres casos:

1. base vacía;
2. base con la versión anterior;
3. segunda inicialización sin cambios.

No use `docker compose down -v` y no restaure pruebas sobre el volumen
operativo. El procedimiento obligatorio está en
`tools/postgres_test_db/README.md`.

## Entrega

Actualice `CHANGELOG.md`, `app/application.py`, README y la nota de continuidad.
Construya una imagen con etiqueta de versión, ejecute la validación completa y
revise `git diff --check`. Producción usa `--no-build` con la imagen ya validada.
