# Planificación de horarios 1.23.0 — actualización del 10 de septiembre de 2026

La planificación sigue siendo diaria y no sustituye ningún dato histórico. Esta
entrega agrega configuración semanal persistente de requeridos, reglas globales
de jornada/descanso, ventanas por equipo, navegación por semana ISO, horarios
base de telefonistas, cruces de medianoche, jornadas partidas, mermas, solicitudes
del agente y auditoría de operaciones.

## Archivos creados

- `app/wfm.py`: validación, cobertura, sugerencia, revisiones y publicación.
- `app/wfm_advanced.py`: compatibilidad y cálculo de segmentos, excepciones y horizonte nocturno.
- `app/wfm.py`: configuración global persistente y normalización no destructiva de demandas legacy.
- `app/static/wfm.js`, `app/static/wfm.css`: planificación y calendario personal.
- `data/wfm/telefonistas-horarios-semanales.json`: plantilla referencial de nombres, turnos y días libres derivada de las capturas.
- `data/wfm/telefonistas-horarios-2026-W37.json`: carga diaria fechada de entrada, salida, descanso, horas extra y novedades para 20 Telefonistas.
- `tests/test_wfm.py`: pruebas aisladas con SQLite en memoria, incluyendo requeridos semanales y ventanas de equipo.
- `tools/wfm_offline_build/Dockerfile`, `README.md`, `package.json`,
  `ui_smoke.cjs`: construcción sin reinstalar dependencias y prueba de interfaz.
- `WFM_IMPLEMENTACION.md`: esta entrega.

## Archivos modificados

- `app/local_server.py`, `app/postgres_server.py`: rutas existentes reutilizadas
  para la nueva configuración y esquema aditivo compartido.
- `app/static/index.html`, `app/static/styles.css`: navegación de Supervisión
  desplegable y caché de assets actualizado.
- `tests/test_postgres_security.py`: publicación, concurrencia y CSRF WFM.
- `tools/postgres_security_test/run.ps1`, `README.md`: imagen candidata opcional.
- `README.md`, `CHANGELOG.md`: operación, alcance y versión.

## Mejoras funcionales

- `wfm_weekly_requirements` conserva siete valores por equipo; los valores
  iniciales del equipo Telefonista son editables y se aplican a planes nuevos.
- La demanda base de Telefonistas se configura entre 05:30 y 22:00, mientras que
  los turnos pueden continuar hasta las 06:00 del día siguiente. Planificadores y
  Supervisores disponen del horizonte completo de 36 horas.
- La barra azul mueve el turno completo respetando duración y punto de agarre;
  durante el gesto muestra una copia semitransparente de tamaño completo con el
  agente y la franja exacta de destino. Descansos y mermas conservan su arrastre
  independiente dentro de la jornada.
- La columna de agentes queda libre de controles. Clic derecho o doble clic
  sobre un turno abre Editar, Dividir y Agregar excepción.
- Publicar semana completa toma todos los borradores guardados de la semana y
  crea sus revisiones publicadas dentro de una única transacción.
- Horarios es de solo lectura, consulta la proyección definitiva creada al
  publicar, integra los registros históricos no sustituidos y su búsqueda cubre
  persona, equipo, turno, horario, nota, excepción y origen al tecleo y a Enter.
- La vista personal resume horas planificadas, operativas y extra; distingue
  «Libre publicado» de «Sin publicación» y muestra los turnos nocturnos en ambos
  días sin repetir información que terminó el día anterior.
- La grilla ofrece año, semana ISO y siete botones diarios; seleccionar un día
  carga el plan correspondiente sin perder el contexto semanal.
- Los planes nuevos resuelven la plantilla de telefonistas por nombre/alias,
  respetan el día libre inicial y excluyen licencias históricas puntuales.
- Registro de auditoría y Planificación de horarios viven dentro de Supervisión.
- Configuración → General permite al Administrador definir duración de jornada y descanso estándar para futuros turnos.
- La fila Diferencia usa rojo intenso para déficits y la fila Requeridos ya no presenta signos de interrogación en la interfaz.
- Auditoría registra guardado de borrador, sugerencias, publicaciones y cambios de configuración WFM.
- Supervisión puede consultar la semana publicada de una persona específica sin alterar el borrador del equipo.
- La tijera conserva las horas planificadas al separar dos bloques y permite moverlos de forma independiente.
- Reunión, Capacitación, Licencia y Ausencia se renderizan dentro de la barra y restan Operativos únicamente donde pisan trabajo.
- El alta rápida inserta una Reunión de 30 minutos; sus bordes ajustan duración
  sobre la grilla y el doble clic edita motivo y nota. El modal detallado sigue
  disponible como alternativa del menú contextual.
- Las solicitudes conservan el horario y la revisión publicados al enviarse,
  rechazan duplicados pendientes y pueden ser canceladas por su autor.
- La bandeja de Supervisión filtra por estado, tipo, fecha, persona o motivo; la
  persona ve una línea de tiempo con autor de la resolución, comentario y horario
  aplicado. Supervisores planificables también pueden crear solicitudes propias.
- Las solicitudes aprobadas generan una nueva revisión publicada; las rechazadas no modifican el plan.
- Una aprobación toma la última publicación vigente y conserva cualquier borrador posterior; la revisión aplicada usa el siguiente número disponible.
- Si hubo una nueva publicación desde el envío, el servidor devuelve un conflicto
  y exige confirmación explícita sobre la revisión vigente antes de aprobar.
- Las ausencias sobre jornadas partidas se separan por bloque. El servidor rechaza excepciones superpuestas o con identificadores repetidos.
- Publicar semana completa muestra el estado y las advertencias de cada día, envía las revisiones esperadas y devuelve conflicto si cambiaron durante la revisión.
- La respuesta del plan incluye cobertura normalizada y el CSV informa horas operativas por segmento.

## Verificación

- `python -B -m unittest discover -s tests -q`: 106 casos ejecutados, con 20
  omisiones esperadas por dependencias o entornos opcionales; las pruebas WFM
  cubren turnos nocturnos, segmentos, mermas y solicitudes.
- `node --check app/static/wfm.js`.
- `node tools/wfm_offline_build/ui_smoke.cjs`: alta, jornada, descanso, arrastre,
  edición y publicación con API simulada y red bloqueada. No equivale a una
  prueba end-to-end autenticada contra los datos reales.
- La suite específica WFM ejecutó 36 casos y la suite general ejecutó 106; ambas
  pasaron en un sistema de archivos temporal. La integración PostgreSQL ejecutó
  20 casos sobre una base temporal sin volumen operativo.
- Imagen candidata construida reutilizando las dependencias locales; la
  construcción habitual con red deshabilitada no pudo ejecutar pip, por lo que
  no se cambió ninguna dependencia ni se descargaron paquetes para resolverlo.
- El smoke de interfaz se ejecuta con API simulada y sin red; la integración
  PostgreSQL usa contenedores temporales sin montar el volumen operativo.

`centro_operativo.db` permanece con SHA-256
`820BB8ACB27A63008F572D61896ED91E6FAC597A9CFE035C36C86F8689D4148C`.
No se actualizó `NOTA_PARA_CONTINUAR_EN_OTRA_PC.md`.

## Alcance pendiente

Copia de planes WFM entre días, intercambio directo de turnos entre agentes y
reglas de cupo/saldo de licencia.
El optimizador es heurístico, no garantiza cero déficit ni una solución global
óptima. Administrador conserva acceso completo por la regla general existente.
