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
   Si la compilación de Vite falla, analiza el log de error de JavaScript, corrige el componente afectado y vuelve a compilar el paquete. No ejecutes una reconstrucción completa de la imagen Docker a menos que se hayan modificado dependencias en el `package.json`.

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
   - **No Overflow Horizontal:** Toda grilla debe ajustarse con `tw-flex-wrap` o scroll interno dentro del componente (`DataTable`), impidiendo que el contenido se desborde o corte botones.
