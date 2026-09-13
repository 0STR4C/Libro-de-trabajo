# Validación completa local

Ejecuta, en orden, la suite general dentro de un contenedor sin red y con el
proyecto montado en modo de solo lectura, la comprobación sintáctica de los
archivos JavaScript y la suite PostgreSQL aislada obligatoria. Si Playwright ya
está instalado en `tools/wfm_offline_build/node_modules`, también ejecuta la
prueba de interfaz con datos simulados; si falta, informa la omisión sin
descargar paquetes.

Desde la raíz del proyecto:

```powershell
& .\tools\test_all\run.ps1
```

Para probar otra imagen local:

```powershell
& .\tools\test_all\run.ps1 -ImageName centro-wfm-candidate:latest
```

Entradas: código del proyecto, una imagen local compatible y las imágenes ya
disponibles que usa `tools/postgres_test_db`. Salidas: resultados en consola y,
si se ejecuta, el perfil temporal que Playwright elimina al terminar. El script
no modifica bases operativas, archivos del proyecto ni servicios de la
aplicación. La suite PostgreSQL crea una base aleatoria, la elimina y detiene su
servidor conservando el volumen y `test_operativa`.

La opción `-Coverage` usa el módulo estándar `trace` para mostrar cobertura por
módulo de la suite general, sin instalar dependencias ni conservar datos. La
cobertura PostgreSQL se evalúa por sus pruebas de integración y no se mezcla con
ese porcentaje, porque corre en otro contenedor y otra base.

La opción `-SkipUiSmoke` omite explícitamente la prueba visual. No sustituye la
suite PostgreSQL y se reserva para entornos que no tengan Playwright.
