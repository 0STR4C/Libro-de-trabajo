# Nota de continuidad — Centro Operativo / Libro de trabajo

## Instrucción para el próximo chat

Estoy continuando el proyecto **Libro de trabajo / Centro Operativo** trasladado desde otra computadora. Antes de modificarlo, lee completos `README.md`, `CHANGELOG.md` y esta nota. Revisa el estado real de los archivos y la base `centro_operativo.db`; no reemplaces ni borres esa base porque contiene los registros operativos trasladados. Mantén compatibilidad con el inicio mediante `Abrir Centro Operativo.bat` y verifica los cambios en `http://127.0.0.1:8000/`.

## Objetivo del sistema

Reemplazar la planilla de operación diaria por una aplicación web con usuarios, roles, trazabilidad y base de datos real. Los módulos actuales son:

- Resumen operativo con métricas y mapa de demoras vigentes.
- Avisos, asignación, gestión, estados y comentarios.
- Zonas con demora, vigentes y normalizadas.
- Programados agrupados por tipo, estados, edición, duplicación y eliminación.
- Horarios semanales en grilla e historial por persona, rol y período.
- Cotizador automático por ubicaciones y manual por kilómetros.
- Tiempos de arribo mediante mapa departamental y detalle por zona/prestación.
- Configuración de usuarios, roles, permisos y tarifas.
- Registro de auditoría reservado al Administrador por defecto.

## Estado actual

- Versión: **1.13.0**, registrada el 7 de septiembre de 2026.
- Implementación activa y validada en esta computadora: `app/postgres_server.py` mediante Docker Compose.
- Base activa: PostgreSQL en el volumen Docker `librodetrabajo_postgres_data`.
- `centro_operativo.db` se conserva intacta como origen histórico protegido; no debe reemplazarse, borrarse ni usarse en paralelo para la operación diaria.
- Interfaz: archivos en `app/static/`.
- Pruebas: `tests/` contiene regresión funcional y seguridad; el intérprete de trabajo pasa 36 pruebas (28 ejecutadas y 8 omitidas por entorno). `tools/postgres_security_test/run.ps1` ejecuta 7 pruebas PostgreSQL sobre una base efímera aislada; todas pasaron.
- El modo local crea una copia diaria consistente en `backups/` antes de inicializar la aplicación, sin sobrescribir ni eliminar copias existentes.
- Usuario inicial histórico: `admin`. La contraseña inicial figura en el README y debe cambiarse antes de producción.
- Dominio corporativo permitido: `@portoservicios.com.uy`.
- OAuth de Google está preparado pero **no configurado**, porque el usuario no tiene permisos de administración de Google Workspace. La aplicación funciona normalmente con correo/usuario y contraseña local.

Docker ejecuta `app/postgres_server.py` con las mismas rutas y reglas funcionales del servidor SQLite. Se agregó `tools/sqlite_to_postgres/` para trasladar la base operativa a un PostgreSQL vacío sin modificar el archivo de origen. El 7 de septiembre de 2026 se reconstruyó el entorno Docker y se restauró el respaldo verificado `postgres-backups/centro_operativo_20260905T043730Z.dump` sobre un volumen nuevo y vacío. Los conteos recuperados fueron 2 usuarios, 1 aviso, 3 zonas de demora, 5 programados, 14 cotizaciones y 48 eventos de auditoría. Los servicios `app`, `db` y `backup` quedaron activos; la aplicación y PostgreSQL están saludables. No se debe ejecutar la migración SQLite sobre ese volumen poblado; el migrador la rechazará de forma segura.

El servicio Docker `backup` genera cada hora un respaldo PostgreSQL verificado en `postgres-backups/`, sin eliminar copias existentes. Administrador y Supervisor pueden descargar reportes CSV de Avisos, Demoras, Programados, Horarios y Cotizaciones; Avisos incluye filtros históricos detallados y Demoras filtros por período, estado, departamento, prestación y texto libre. Horarios conserva registros semana a semana, filtra por persona, rol y período, impide duplicados o superposiciones incluso después de medianoche y permite copiar la semana anterior sin reemplazar registros existentes. La grilla precarga persona y fecha al agregar desde una celda; también se configura desde el modal de **Configuración → General**. El cotizador separa coberturas Asegurado/No asegurado y las tarifas se editan en pestañas por cobertura; los campos de cerrajería desp. 22 hs con costo cero ya no se muestran. El Administrador también puede descargar el Registro de auditoría. Para un servidor definitivo todavía se debe configurar un destino externo, retención y recuperación continua mediante WAL/PITR.

Se preparó una etapa adicional de seguridad en `app/security.py`, `app/schemas.py` y `app/postgres_server.py`: secretos de producción con cierre preventivo, cookies HttpOnly/CSRF, vencimiento y revocación de sesiones, límite de intentos, validación Pydantic, Trusted Host, encabezados de seguridad, límite de cuerpo y documentación API deshabilitada por defecto en producción. También se agregaron `SECURITY.md`, `DEPLOY_REMOTE_PRIVATE.md` y `tests/test_postgres_security.py`. Se corrigió la interacción de los botones internos para que la CSP no bloquee las acciones dinámicas, sin `eval` ni `unsafe-inline`; el ejecutable de escritorio reconstruye `app` y sirve `app.js?v=25` con los filtros de Demoras, la interfaz del cotizador y Horarios. La fuente está compilada y el backend FastAPI/PostgreSQL fue validado dentro del contenedor temporal aislado.

El contenedor activo fue reconstruido con la versión 1.13.0 y respondió `/health`; `app`, `db` y `backup` quedaron activos y saludables. No usar `docker compose down -v`, no restaurar sobre `librodetrabajo_postgres_data` y no tocar `centro_operativo.db` (hash protegido actual: `820BB8ACB27A63008F572D61896ED91E6FAC597A9CFE035C36C86F8689D4148C`). La suite PostgreSQL temporal pasó y su contenedor efímero fue eliminado.

## Decisiones operativas importantes

- Una demora normalizada no aparece en el mapa principal; solamente cuentan las vigentes.
- El color del mapa aumenta según las demoras propias y la concentración en departamentos vecinos.
- El rol Administrador siempre tiene todos los permisos y no puede desmarcarlos.
- Los demás roles pueden configurarse y pueden crearse roles nuevos.
- El Registro de auditoría contiene acciones administrativas; no es el historial operativo de cada módulo.
- Los registros de tarea enlazan a `https://aps.portoservicios.uy/3/tareas/{tarea}`.
- Cada cálculo del cotizador genera una única fila de historial. Puede recuperarse sin modificar el original.
- El formulario del cotizador mantiene un borrador local automático y permite copiar el resumen.
- Las cotizaciones anteriores a la versión 1.7.0 no tienen número de tarea; deben mostrarse como “Sin tarea”.
- El menú de tres puntos siempre debe ordenar las acciones con **Eliminar al final**.

## Cómo abrirlo en la otra computadora

1. Extraer la carpeta completa manteniendo el nombre `Libro de trabajo`.
2. Abrir esa carpeta como proyecto en Codex.
3. Enviar al nuevo chat: **“Lee completa `NOTA_PARA_CONTINUAR_EN_OTRA_PC.md`, `README.md` y `CHANGELOG.md`, revisa el proyecto y continúa desde la versión 1.13.0 sin perder la base de datos.”**
4. Para ejecutar el modo validado, hacer doble clic en `Abrir Centro Operativo.bat` desde una computadora que tenga disponible el entorno local de Codex.
5. Si el iniciador no encuentra Python, pedir al nuevo chat que adapte el lanzador al entorno de esa computadora o que complete el despliegue Docker.

## Archivos que no deben perderse

- `centro_operativo.db`: datos operativos y configuración.
- `app/`: backend e interfaz.
- `tests/`: pruebas de regresión.
- `README.md` y `CHANGELOG.md`: operación y versiones.
- `workbook-analysis/`: material visual del relevamiento original.
- `Dockerfile`, `compose.yaml`, `.env.example`: base del despliegue en contenedores.
- `tools/desktop_launcher/`: fuente, instrucciones y ejecutable del lanzador Windows.

## Verificación recomendada al retomar

1. Confirmar que se haya creado la copia diaria de `centro_operativo.db` en `backups/`.
2. Ejecutar las pruebas antes de modificar.
3. Abrir la herramienta y revisar Resumen, Avisos, Demoras, Programados, Cotizador, Tiempos de arribo, Roles y Log.
4. Confirmar que los usuarios trasladados mantienen sus roles.
5. Mantener actualizado `CHANGELOG.md` y aumentar la versión visible en `app/local_server.py` para cada entrega importante.

## Próximas prioridades técnicas sugeridas

- Definir credenciales definitivas, destino externo, retención y recuperación WAL/PITR antes del uso en producción.
- Ejecutar la prueba de restauración en una base PostgreSQL temporal separada y registrar el resultado sin alterar el volumen activo.
- Definir objetivos de recuperación (RPO/RTO) y comprobar que el procedimiento documentado los cumple.
- Definir si los reportes operativos definitivos requieren formato XLSX además de los CSV compatibles con Excel.
- Definir la política operativa de archivo externo y conservación de las copias automáticas.
- Cambiar la contraseña inicial y asignar correos corporativos a las cuentas existentes.
- Completar los tiempos de arribo de todos los departamentos y zonas.
- Validar catálogos definitivos de prestaciones, estados y destinatarios.
