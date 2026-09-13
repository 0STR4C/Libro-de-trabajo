# Comprobación de portabilidad

Comprueba que estén los archivos técnicos necesarios para continuar el proyecto
en otra computadora. Puede exigir la base SQLite o un dump PostgreSQL con su
checksum y, opcionalmente, una imagen Docker local. No abre `.env`, bases, dumps
ni JSON operativos; solo comprueba su presencia.

Desde la raíz:

```powershell
& .\tools\portability_check\run.ps1
& .\tools\portability_check\run.ps1 -DataMode PostgreSQL -RequireImage
```

Entradas: carpeta actual, modo de datos y nombre opcional de imagen. Salida: un
objeto `OK` con versión y cantidad de fuentes WFM opcionales ausentes. La
herramienta es de solo lectura y no modifica archivos, contenedores ni datos.

Use `ProjectOnly` para revisar una copia de código, `SQLite` cuando se trasladará
`centro_operativo.db` y `PostgreSQL` cuando se trasladará el dump más reciente.
El procedimiento completo está en `DATA_MANIFEST.md`.
