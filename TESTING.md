# Cobertura y matriz de pruebas

La validación de la entrega 1.30.0 descubrió 200 pruebas generales: 172 se
ejecutaron en el contenedor sin red y 28 se omitieron allí porque pertenecen a
la integración PostgreSQL. Esas 28 se ejecutaron después contra una base nueva
y aislada. JavaScript y la prueba de interfaz sintética también pasaron.

`tools/test_all/run.ps1 -Coverage` usa `trace`, incluido en Python, y en la
última corrida informó 100 % de líneas instrumentadas para los módulos cargados.
Ese dato no mide ramas, JavaScript ni el proceso PostgreSQL separado; por eso no
se usa como único criterio de calidad.

| Riesgo | Verificación |
| --- | --- |
| Reglas de dominio SQLite | Suite general y APIs locales temporales |
| Paridad y seguridad PostgreSQL | 28 integraciones sobre base aleatoria |
| Inicialización y upgrade | Checksums, base nueva e inicialización repetida |
| Producción | Secretos, HTTPS, hosts/orígenes, cookies Secure y API docs |
| Interfaz | Sintaxis Node y smoke Playwright con red bloqueada |
| Restauración | Dump y checksum, restricciones, referencias, secuencias e inicialización |
| Portabilidad | Manifiesto técnico, datos locales e imagen opcional |

Quedan fuera de la automatización la emisión y renovación real del certificado
TLS, Google Workspace y OSRM, porque dependen de servicios e infraestructura
externos. Las pruebas reemplazan esas respuestas y conservan el modo manual de
distancia. Antes de producción, el responsable de infraestructura debe probar
la URL HTTPS desde otra PC y el ingreso corporativo si se habilita.
