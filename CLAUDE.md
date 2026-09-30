# REGIONAL DIRECTIVES & AGENT RULES: LIBRO DE TRABAJO

---

## 1. PROTOCOLO DE EJECUCIÓN Y OPTIMIZACIÓN DE RECURSOS (STRICT)

Para evitar consumo innecesario de tokens, cómputo y bucles de espera:

1. **Plan A Directo en Docker (CERO intentos en Host):**
   Queda estrictamente PROHIBIDO intentar ejecutar intérpretes de Python, scripts de validación o entornos directamente en el sistema HOST. El runtime único es la imagen/contenedor Docker local. Prohibido perder tiempo haciendo comprobaciones de fallback en el Host.

2. **Aislamiento de Pruebas según el Alcance (Scoped Testing):**
   - **Para tareas de Frontend / UI / CSS / Layout:** Ejecuta ÚNICAMENTE la compilación del bundle mediante `vite build` y verificación de sintaxis JS/JSX.
   - **PROHIBICIÓN:** Queda terminantemente PROHIBIDO correr la suite general de pruebas unitarias en Python o las pruebas de integración de PostgreSQL cuando el cambio sea puramente visual o de maquetación de componentes.

3. **Diagnóstico Ligero de Compilación:**
   Si la compilación de Vite falla, analiza el log de error de JavaScript, corrige el componente afectado y vuelve a compilar el paquete.

4. **Reconstrucción obligatoria de la aplicación:**
   Toda modificación de código que afecte el funcionamiento de la aplicación debe finalizar con una reconstrucción completa de la imagen de Docker (ej. `docker compose up -d --build`). Queda estrictamente prohibido aplicar parches copiando archivos temporalmente a un contenedor en ejecución sin reconstruir su imagen base.

---

## 2. DIRECTIVAS GLOBALES DE DISEÑO UI/UX (PRIMEREACT + TAILWIND)

Toda la interfaz debe seguir un estándar de software B2B de alta densidad:

1. **Sistema de Componentes:**
   Se utilizarán componentes nativos de **PrimeReact** (DataTables, Dialogs, Dropdowns) combinados con clases utilitarias de **Tailwind CSS** (utilizando el prefijo `tw-` y el aislamiento configurado).

2. **Estructura Visual y Colores:**
   - **Sidebar:** Azul marino oscuro corporativo (`#0f172a`).
   - **Header:** Área de usuario cliqueable, botón **'Salir' en color rojo** de alerta, y el selector de tema **(Claro / Oscuro / Sistema)** visible y funcional. Eliminado el indicador `'Sistema activo'`.
   - **Acción Primaria:** Azul corporativo (`#1677ff` / `#2563eb`).
   - **Estados Semánticos:** Rojo (`--color-urgente`), Ámbar/Naranja (`--color-espera`), Verde (`--color-ok`).

3. **Limpieza Universal de Encabezados:**
   Queda prohibido incluir subtítulos descriptivos debajo del título principal de las pestañas (ej. "Lo que el equipo necesita atender ahora", "Registrar, asignar, gestionar...", etc.). Los títulos deben ir limpios.

4. **Alta Densidad y Control de Layout:**
   - Filas de tablas compactas (36px a 40px), tipografía base de 13px/14px, tarjetas con paddings reducidos (`tw-p-4`) y sombras finas (`tw-shadow-sm`).
   - **No Overflow Horizontal:** Las vistas de lectura deben ajustar sus columnas y permitir saltos de línea sin desplazamiento horizontal. Las grillas estratégicas de planificación pueden usar scroll interno del componente cuando el eje temporal lo requiera, sin desbordar la página.

## 3. CONTRATO EXCLUSIVO DE DESARROLLO FRONTEND

1. **Pila exclusiva:** construir componentes en JSX, con React, componentes nativos de PrimeReact y utilidades Tailwind CSS. No crear ni recuperar `DomSlot`, plantillas HTML inyectadas, controles legacy ni parches en `app.js` para resolver componentes.
2. **Estilos dentro del componente:** queda prohibido resolver el layout de un componente con CSS global genérico en `styles.css` u otras hojas globales. Aplicar clases Tailwind en JSX y las propiedades nativas o Pass Through (`pt`) de PrimeReact. Los tokens globales existentes no autorizan parches por pantalla.
3. **Telefonistas:** alta densidad, lectura rápida sin scroll horizontal y acciones directas para atender llamadas, registrar avisos y comunicar demoras.
4. **Planificadores:** visión estratégica, grillas precisas, asignaciones y gestión de programados.
5. **Densidad B2B:** `tw-text-[13px]` o `tw-text-sm`, `tw-p-4` y `tw-gap-3`; toda DataTable debe usar `size="small"` y `stripedRows`.
6. **Texto y tablas:** textos largos con `tw-whitespace-normal tw-break-words` (equivalentes a `white-space: normal` y `overflow-wrap: break-word`). Reservar anchos mínimos explícitos para columnas compactas. Fechas y horas son la excepción: `tw-whitespace-nowrap` para conservar la unidad de lectura. No ocultar información ni superponer celdas.
7. **Elementos flotantes:** Dropdown, Calendar y demás selectores con panel deben declarar `appendTo={document.body}`. Gestionar capas mediante PrimeReact; evitar contenedores que recorten el panel. Calendar conserva su estructura flex nativa y usa `showIcon`.
8. **Layout:** botoneras con `tw-flex tw-flex-wrap tw-items-center tw-gap-3 tw-w-full`. No usar márgenes negativos, posiciones absolutas ni anchos rígidos para acomodar controles. Responsable y acción de asignación usan `tw-flex tw-flex-col tw-items-start tw-justify-center tw-gap-1 tw-w-full`.
9. **Configuración vigente:** Tailwind usa prefijo `tw-`, `important: true` para utilidades y Preflight desactivado. Las utilidades también funcionan en portales bajo `document.body`; no asumir aislamiento por `#prime-react-root`.
10. **Fuente de verdad:** `AGENTS.md` y `CLAUDE.md` deben conservar contenido idéntico. Las guías históricas y recomendaciones de skills no desplazan estas reglas ni las instrucciones explícitas del usuario. Validación frontend: Vite y sintaxis JS/JSX en Docker.

## 4. CONTRATO DE EMPAQUETADO PARA SERVIDOR

Para cada ZIP de servidor usar `tools/deployment/package_server.py` y su guía
`tools/deployment/README.md`. Conservar el perfil de Sistemas `sistemas-20260925`:
APP_PORT configurable en ambos Compose (8000 interno), identidad estable del
proyecto, logs json-file de 10 MB × 3 por servicio, init y no-new-privileges para
app, margen inicial de salud de 60 s y espera de arranque de 240 s. La plantilla
incluye COMPOSE_PROJECT_NAME y BACKUP_MAX_AGE_SECONDS. Validar la mezcla Compose
con valores sintéticos y puerto alternativo, sin reiniciar la operación local.
No incluir secretos, datos ni backups en el ZIP ni reemplazar el .env del servidor.
Preservar el nombre Compose y los volúmenes de la instalación existente; el nombre
sugerido para una instalación nueva no autoriza renombrar un despliegue activo.
Generar nuevamente manifiesto y checksum; nunca reutilizar los de un ZIP anterior.
