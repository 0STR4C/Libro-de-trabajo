# UI UX Pro Max · Integración de desarrollo

## Propósito y alcance

Conservar un protocolo reutilizable para aplicar la instalación local de UUPM a
Libro de Trabajo y un mensaje inicial para **11 · Interfaz y experiencia de uso**.
La fuente editable de esa plantilla es [PROMPT_11.md](PROMPT_11.md): copiar su
contenido en la conversación del área. Las demás áreas también deben consultar
esta guía cuando modifiquen una interfaz.

UUPM orienta decisiones de diseño mediante archivos y búsquedas locales. No está
integrado al backend en ejecución ni agrega endpoints, tablas o servicios.
Guardar la skill en `.claude/skills/` no demuestra que un agente la haya cargado:
las instrucciones requieren leerla explícitamente.

## Fuentes y precedencia

1. Solicitud del usuario, `AGENTS.md` y restricciones del proyecto.
2. Arquitectura, identidad y decisiones visuales ya acordadas.
3. [Instrucciones UUPM](../../.claude/skills/ui-ux-pro-max/SKILL.md) y referencias
   pertinentes para la pantalla.
4. Resultados locales de búsqueda, verificados como recomendaciones aplicables.

Leer [ARCHITECTURE.md](../../ARCHITECTURE.md),
[ARCHITECTURE.md](../../ARCHITECTURE.md).
Para web, la referencia transversal es
[`quick-reference.md`](../../.claude/skills/ui-ux-pro-max/references/quick-reference.md).
`references/pro-rules.md` declara un alcance nativo/móvil; adaptar únicamente sus
reglas pertinentes, sin imponer requisitos de iOS o Android a esta aplicación web.

El desarrollo frontend usa JSX en `frontend/`, React, PrimeReact y Tailwind.
Es obligatorio el contrato B2B de `AGENTS.md`/`CLAUDE.md`: alta densidad para
Telefonistas, grillas precisas para Planificadores, tablas pequeñas y alternadas,
textos largos con salto de línea, y Dropdown/Calendar `appendTo={document.body}`.
No usar parches de CSS global ni lógica legacy para resolver componentes.
Las recomendaciones de la skill se adaptan a estas directivas explícitas.

## Requisitos e instalación

- La skill ya está instalada en
  `D:\Codex\Libro de trabajo\.claude\skills\ui-ux-pro-max`.
- Su buscador declara Python 3.x y usa la biblioteca estándar; no requiere
  instalar paquetes Python externos. No se crea otro archivo de dependencias
  porque este directorio contiene documentación y una plantilla de instrucciones.
- El único runtime permitido es Docker: no probar intérpretes en el host.
  Para consultas del catálogo puede usarse Python de la imagen local
  `librodetrabajo-app:latest`, con Docker disponible, sin descargar imágenes ni
  conectar bases de datos.
- Si falta el intérprete y Docker no está disponible, leer las referencias y
  declarar pendiente la búsqueda ejecutable. Instalar software o descargar
  recursos requiere la autorización correspondiente.

## Consulta mínima y ejemplo verificable

Consulta del catálogo con la imagen Docker ya instalada (no es una prueba del proyecto):

```powershell
docker run --rm --pull=never --network none --read-only --cap-drop ALL --security-opt no-new-privileges --mount "type=bind,source=D:\Codex\Libro de trabajo\.claude\skills\ui-ux-pro-max,target=/uupm,readonly" --entrypoint python librodetrabajo-app:latest -B /uupm/scripts/search.py "keyboard focus modal" --domain ux -n 2
```

Comprobar salida exitosa, dominio `ux`, fuente `ux-guidelines.csv` y resultados
pertinentes sobre foco o teclado en modales. El código de salida por sí solo no
demuestra una coincidencia útil: revisar también el contenido. Si está vacío o
fuera de tema, reformular una vez. Si vuelve a fallar, informar que no hay una
coincidencia verificada y distinguir las referencias generales de los resultados.

Para una página nueva o una dirección global, generar primero una propuesta sin
escribir archivos:

```powershell
python -B "D:\Codex\Libro de trabajo\.claude\skills\ui-ux-pro-max\scripts\search.py" "internal operations dashboard" --design-system -p "Libro de Trabajo" -f markdown
```

No es una orden de rediseñar el producto ni de adoptar toda la salida. Revisar su
encaje con los usuarios, la densidad operativa y la identidad azul/turquesa.

## Decisiones compartidas y persistencia

Si existe `design-system/<project-slug>/MASTER.md`, leerlo antes de proponer cambios.
Las reglas de `pages/<page-name>.md` prevalecen sobre Master en esa página, sin
desplazar las instrucciones del usuario ni las restricciones del proyecto.

Solo al guardar decisiones verificadas, usar `--persist` con
`--output-dir "D:\Codex\Libro de trabajo"`; la salida queda bajo
`design-system/<project-slug>/`. Comprobar la ruta producida y reutilizar el mismo
directorio entre conversaciones. La skill preserva los archivos existentes salvo
que se use `--force`, que exige autorización explícita. No se generó un Master
como parte de esta integración documental.

El apartado 11 mantiene criterios comunes de color, tipografía, espaciado,
componentes y accesibilidad. Las otras áreas los aplican y documentan las
excepciones. Delimitar archivos antes de editar y coordinar cambios en estilos
globales o JavaScript compartido. Las suites que arrancan y detienen la misma
instancia PostgreSQL de pruebas deben ejecutarse de una en una.

## Entradas, salidas y archivos que puede modificar

- **Plantilla:** entrada = solicitud UI/UX y contexto del proyecto; salida =
  instrucciones para el agente. Leerla no modifica archivos.
- **Consulta:** entrada = términos genéricos y catálogos de la skill; salida =
  recomendaciones en consola. Los ejemplos no usan `--persist` y `-B` evita
  generar bytecode Python. El ejemplo Docker monta solo la skill en lectura.
- **Persistencia opcional:** puede crear Master y excepciones bajo
  `design-system/<project-slug>/`; con `--force` puede reemplazarlos.
- **Implementación posterior:** puede modificar los archivos frontend y pruebas
  necesarios para la solicitud autorizada, preservando cambios anteriores.

No introducir nombres de personas, datos operativos, credenciales ni información
privada en consultas o sistemas de diseño persistidos. Las búsquedas locales no
requieren red. Las sugerencias de fuentes, imágenes o librerías no autorizan
acceso externo.

## Validación y estado de esta entrega

Después de una implementación, ejecutar las pruebas apropiadas y siempre:

```powershell
& "D:\Codex\Libro de trabajo\tools\postgres_test_db\run.ps1"
```

Usar la base nueva por corrida de `librodetrabajo-tests`, conservar `test_operativa`
y el volumen de pruebas. Añadir verificación visual con datos sintéticos,
teclado, foco, contraste, estados de error y carga, y anchos móvil/escritorio.
Registrar lo que no pudo comprobarse; una recomendación no certifica accesibilidad.

El 23/09/2026, después de iniciar Docker Desktop, se completó la verificación
ejecutable usando la imagen local `librodetrabajo-app:latest`, sin red, con la
skill montada en solo lectura y sin persistir resultados:

- `"keyboard focus modal" --domain ux -n 2`: salida exitosa y dos resultados de
  `ux-guidelines.csv`, `Focus States` y `Focus Not Obscured (Enhanced)`. Ambos son
  pertinentes para foco y teclado; el segundo identifica expresamente su nivel
  AAA, que no debe presentarse como requisito AA.
- `"internal operations dashboard" --design-system`: salida exitosa, pero el
  patrón `Hero + Features + CTA` corresponde a una página comercial y no constituye
  una propuesta global verificada para esta herramienta operativa.
- Se reformuló una vez como `"dispatch operations dense dashboard"`: devolvió el
  estilo pertinente `Data-Dense Dashboard`, pero conservó un patrón comercial
  `Enterprise Gateway`. No se encontró una propuesta global íntegramente adecuada
  en esos dos intentos; no se adoptó ni se persistió ninguno de los resultados.

El buscador local queda verificado. Para próximas tareas, priorizar consultas
enfocadas por dominio y contrastar cada recomendación con la pantalla real. El
generador global funciona, pero su salida requiere selección y revisión contextual;
no demuestra por sí sola que el diseño propuesto sea adecuado.

Esta entrega modifica solo documentación; no requiere ejecutar la suite PostgreSQL
ni desplegar la aplicación. No se modificaron la interfaz, las bases operativas
ni los archivos de la skill.
