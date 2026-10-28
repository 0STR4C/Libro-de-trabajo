# Revisión de vigencia de Demoras

El proceso que creaba Avisos automáticos por revisiones vencidas fue retirado. `compose.yaml` y `compose.production.yaml` ya no definen `delay-review-worker`. La invocación histórica `python -m app.delay_review_worker` termina sin conectarse a la base ni escribir datos.

La revisión pendiente se calcula desde `next_review_at` (con las alternativas históricas existentes) y se consulta en `GET /api/delays` y `GET /api/dashboard/map-stats`. Una demora vencida continúa vigente hasta su normalización. Verificar y normalizar registran eventos y auditoría de la demora, sin crear ni cerrar Avisos. Los avisos históricos existentes no se borran ni se migran.

Para verificar el comportamiento usá PostgreSQL aislado con `tools/postgres_test_db/run.ps1` y `tests/test_delay_api_pytest.py`. No ejecutes un worker periódico para gestionar revisiones de Demoras.
