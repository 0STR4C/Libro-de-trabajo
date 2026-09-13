# Instrucciones de trabajo del proyecto

## Validación obligatoria de mejoras

Cuando se modifique código, esquema, configuración o interfaz del proyecto:

1. Preservar los cambios existentes y trabajar únicamente dentro de este proyecto.
2. Ejecutar las pruebas generales apropiadas para el cambio.
3. Ejecutar siempre la suite PostgreSQL aislada antes de dar la mejora por terminada:

   ```powershell
   & .\tools\postgres_test_db\run.ps1
   ```

4. El comando debe iniciar `librodetrabajo-tests-test-db-1`, crear una base nueva
   para esa corrida, ejecutar las pruebas y detener el servidor al finalizar.
5. Conservar el volumen de pruebas y la base manual `test_operativa`; no usar,
   limpiar ni modificar la base PostgreSQL operativa para ejecutar pruebas.
6. Si la suite falla, corregir el problema y repetirla. Informar claramente todo
   fallo que no pueda resolverse.

La herramienta y sus datos de conexión están documentados en
`tools/postgres_test_db/README.md`.
