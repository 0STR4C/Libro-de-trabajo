# Política propuesta de respaldo y restauración

## Alcance

Protege la base operativa local `centro_operativo.db` y, cuando se active el despliegue multiusuario, la base PostgreSQL. Una copia guardada en el mismo disco no protege frente a rotura, pérdida, ransomware o daño físico del equipo.

## Esquema recomendado

- Crear una copia local diaria antes del primer inicio de Centro Operativo cuando se use SQLite.
- Confirmar cada operación inmediatamente en PostgreSQL y generar adicionalmente un `pg_dump` verificado cada hora. Esta función ya está activa en Docker.
- Replicar las copias a un repositorio corporativo cifrado ubicado fuera de la computadora de operación.
- Conservar 7 copias diarias, 4 cierres semanales y 12 cierres mensuales.
- No permitir que usuarios operativos modifiquen o eliminen el repositorio externo.
- Cifrar la transferencia y el almacenamiento; custodiar las claves fuera de la carpeta del proyecto.
- Registrar fecha, tamaño, hash, resultado de integridad y responsable de cada copia.
- En el servidor definitivo, habilitar archivo continuo de WAL/PITR para reducir el punto máximo de pérdida a cinco minutos o menos.

## Restauración

- Probar trimestralmente una restauración en un entorno aislado.
- Verificar integridad, recuentos por tabla, usuarios y roles antes de declarar válida la restauración.
- Nunca restaurar directamente sobre la base activa: recuperar en un archivo o base nuevos, validar y efectuar el cambio mediante una ventana aprobada.

## Decisiones pendientes

La organización debe elegir el destino corporativo, responsables, cifrado, horario y plazo legal de conservación. La eliminación por antigüedad no está automatizada hasta que esas decisiones sean aprobadas.
