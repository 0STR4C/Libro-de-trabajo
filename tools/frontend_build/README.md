# Compilación frontend PrimeReact + Tailwind CSS

Vite compila JSX de `frontend/` y genera `app/static/frontend/`. Todo desarrollo
usa React, componentes PrimeReact y utilidades Tailwind; no se admite fallback
HTML ni parches de componentes en CSS global. Aplicar `AGENTS.md` y `CLAUDE.md`.

## Requisitos

Docker Desktop y la imagen local `librodetrabajo-frontend-check`, con Node y las
dependencias de `package-lock.json`. No ejecutar Node ni Python en el host.
Si cambian dependencias, reconstruir la etapa frontend del Dockerfile con
`npm ci`; las descargas requieren la autorización correspondiente.

## Compilación sin reconstruir la imagen

Desde la raíz del proyecto en PowerShell:

```powershell
docker run --rm --pull=never --network none --mount "type=bind,source=${PWD}/frontend,target=/build/frontend,readonly" --mount "type=bind,source=${PWD}/app/static,target=/build/app/static" --mount "type=bind,source=${PWD}/tailwind.config.js,target=/build/tailwind.config.js,readonly" --mount "type=bind,source=${PWD}/postcss.config.js,target=/build/postcss.config.js,readonly" --mount "type=bind,source=${PWD}/vite.config.js,target=/build/vite.config.js,readonly" librodetrabajo-frontend-check npm run build:frontend
```

Entradas: `frontend/`, los recursos de `app/static/` y las tres configuraciones
montadas. Salidas reemplazables: `app/static/frontend/prime-react.js`,
`prime-react.css` y fuentes bajo `app/static/frontend/assets/`. No modifica datos
operativos ni archivos fuente. Las versiones están en `package-lock.json`.

## Estilo y validación

Tailwind mantiene prefijo `tw-`, `important: true` y Preflight desactivado; las
utilidades alcanzan portales bajo `document.body`. PrimeReact usa Lara Light Blue.
Telefonistas necesitan lectura densa sin scroll horizontal; Planificadores,
grillas precisas. Usar `tw-text-[13px]` o `tw-text-sm`, `tw-p-4`, `tw-gap-3`,
DataTable `size="small"` con `stripedRows`, textos largos con salto de línea,
fechas sin cortes y Dropdown/Calendar `appendTo={document.body}`.

La validación frontend se limita a Vite y sintaxis JS/JSX en Docker. No ejecutar
suites Python ni PostgreSQL para UI. No reconstruir toda la imagen ante errores
de JSX: corregir el componente y repetir la compilación.

## Inventario conservado de CSS heredado

`audit_css.cjs` compara selectores CSS con las fuentes JSX y el shell activo.
Requiere la misma imagen Docker de compilación; usa PostCSS 8.5.28 y
postcss-selector-parser 6.1.5 resuelto por `package-lock.json`. No necesita instalación
adicional ni red. Es una heurística de candidatos, no prueba de ausencia en el DOM:
revisar cada resultado, sobre todo clases generadas por datos o bibliotecas.

Desde la raíz en PowerShell, inventario de solo lectura:

```powershell
docker run --rm --pull=never --network none --mount "type=bind,source=${PWD},target=/project,readonly" librodetrabajo-frontend-check node /project/tools/frontend_build/audit_css.cjs /project
```

Entradas: `frontend/*.jsx`, `app/static/index.html`, `app.js`, `branding.js` y las
hojas propias styles/operations/dashboard/quotes/settings/auth. Salida: JSON por
stdout. `--apply` escribe exclusivamente esas hojas; para usarlo después de
revisar candidatos, quitar `,readonly` del montaje y agregar `--apply` al final.
No procesa vendor, el bundle generado, datos operativos ni `legacy_archive`.

Ejemplo verificable: `.elemento-retirado{color:red}` es candidato si ninguna
fuente menciona ese nombre; `.p-button` se conserva como clase de PrimeReact.
Después de aplicar, ejecutar Vite; revisar siempre el diff y los cambios de UI.
