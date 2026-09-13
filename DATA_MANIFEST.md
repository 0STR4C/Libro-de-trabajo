# Manifiesto de datos locales

Los archivos bajo `data/` contienen entradas operativas locales y están
excluidos de Git. No forman parte de una clonación ni de un archivo generado
solo con archivos versionados.

La funcionalidad WFM puede consumir:

| Ruta | Propósito | Obligatorio |
| --- | --- | --- |
| `data/wfm/telefonistas-horarios-semanales.json` | Plantilla semanal por persona | Solo para precarga |
| `data/wfm/telefonistas-horarios-AAAA-Www.json` | Excepciones fechadas de una semana ISO | Solo para esa importación |

Para trasladar el proyecto, copie `data/` por un canal interno autorizado y
compruebe que los JSON estén presentes antes de construir la imagen. No agregue
estos archivos a Git ni los incluya en diagnósticos. Si no se trasladan, la
aplicación conserva los datos ya persistidos, pero no podrá repetir esas
precargas desde los archivos fuente.

También deben trasladarse por separado, según el modo elegido:

- SQLite: `centro_operativo.db` y los respaldos necesarios;
- PostgreSQL: un `pg_dump` con su archivo `.sha256`, nunca el directorio interno
  del volumen;
- producción: `.env` mediante el gestor seguro de configuración, sin guardarlo
  en el repositorio.

Después del traslado, ejecute la restauración en un volumen nuevo, valide el
healthcheck y corra `tools/test_all/run.ps1` antes de habilitar usuarios.

Antes de copiar puede comprobar el conjunto esperado sin abrir los datos:

```powershell
& .\tools\portability_check\run.ps1 -DataMode PostgreSQL -RequireImage
```
