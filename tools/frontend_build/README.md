# Compilación frontend PrimeReact + Tailwind CSS

## Propósito

Prepara la migración gradual de las pantallas de Libro de Trabajo a React y
PrimeReact sin alterar la lógica heredada. Vite compila el punto de entrada de
`frontend/` y deja los artefactos estáticos en `app/static/frontend/`.

La migración progresiva carga esos artefactos en `#prime-react-root`. El Header
monta el selector Claro/Oscuro/Sistema; Resumen usa tarjetas PrimeReact y Avisos
incorpora tarjetas métricas más `DataTable`. Ambas vistas reciben datos o nodos
ya generados por la aplicación heredada. De este modo se renueva la capa visual
sin duplicar eventos, estado ni llamadas a la API. Si el módulo no puede
cargarse, cada pantalla conserva la estructura heredada como respaldo.

## Requisitos e instalación

- Node.js 20.19 o 22.12 o posterior y npm.
- Acceso al registro de npm solo durante la instalación.

Desde la raíz del proyecto:

```powershell
npm ci
```

Las versiones exactas se conservan en `package.json` y `package-lock.json`.
`node_modules/` permanece excluido de Git.

## Uso

```powershell
npm run build:frontend
```

Entradas:

- `frontend/main.jsx`: integración de React, PrimeReact, tema e íconos;
- `frontend/tailwind.css`: capas de Tailwind sin estilos base;
- `tailwind.config.js`, `postcss.config.js` y `vite.config.js`;
- clases encontradas en `frontend/` y `app/static/`.

Salidas reemplazables:

- `app/static/frontend/prime-react.js`;
- `app/static/frontend/prime-react.css`;
- fuentes de PrimeIcons bajo `app/static/frontend/assets/`.

La compilación puede reemplazar únicamente `app/static/frontend/`. No modifica
las bases de datos ni los archivos fuente. Los artefactos se generan también en
la etapa Node del Dockerfile y se copian a la imagen Python final.

Vite usa `/static/frontend/` como base pública para que las fuentes de
PrimeIcons e Inter se resuelvan desde el mismo directorio estático.

## Aislamiento del CSS heredado

Tailwind usa el prefijo `tw-`, genera reglas bajo `#prime-react-root` y tiene
`corePlugins.preflight` desactivado. El archivo de entrada omite además
`@tailwind base`. No quitar esas protecciones hasta completar una revisión
visual de las pantallas heredadas y migradas.

El modo oscuro se activa con la clase `tw-dark`, conserva la preferencia en
`localStorage` y, al elegir Sistema, sigue los cambios de
`prefers-color-scheme`. Las variables globales de `styles.css` mantienen los
colores semánticos de urgencia, espera y resolución en ambos temas.

Los estilos de PrimeReact se aplican a sus clases `p-*`. El tema elegido para la
base de migración es `lara-light-blue`, coherente con la identidad azul actual.

## Docker y validación

El Dockerfile instala dependencias mediante `npm ci`, ejecuta la compilación y
copia solo la salida estática a la imagen de aplicación. Para validar una imagen
candidata sin tocar el contenedor activo:

```powershell
docker build --tag librodetrabajo-app:frontend-candidate .
& .\tools\test_all\run.ps1 -ImageName librodetrabajo-app:frontend-candidate
```

Después de validar una implementación de interfaz, la suite PostgreSQL aislada
continúa siendo obligatoria. Nunca debe usarse la base operativa para pruebas.
