# Alta aditiva del equipo

Utiliza el backend PostgreSQL ya instalado; versiones en `requirements.txt` del
proyecto (sin dependencias adicionales). No instala software ni inicia servicios.

Entrada JSON por stdin: lista de `{"name":"Persona de ejemplo","email":"ejemplo@portoservicios.com.uy"}`.
No incluir listados reales ni credenciales en esta carpeta reutilizable.

Desde la raíz, con el contenedor app actualizado y activo:

```powershell
Get-Content -Raw data/onboarding/telefonistas-20260908.json | docker compose exec -T app python -m tools.user_onboarding.import_users
Get-Content -Raw data/onboarding/telefonistas-20260908.json | docker compose exec -T app python -m tools.user_onboarding.import_users --apply
```

El primer comando comprueba sin insertar. El segundo crea cuentas nuevas activas
como Telefonista y registra auditoría en una única transacción. Usa una misma
contraseña aleatoria temporal para el lote, con hash y sal independiente por
cuenta. **No muestra ni guarda la contraseña**: el Administrador debe establecer
una nueva desde Configuración → Usuarios → Editar antes de entregar accesos.

Conserva cualquier usuario que coincida por correo o usuario alternativo, sin
cambiar contraseña, rol o nombre. Repetir el mismo listado no crea duplicados.
Salida: conteos agregados. Solo escribe `users` y `audit_log` mediante el backend;
no lee ni modifica SQLite, backups, roles, archivos de claves ni credenciales.
La conexión usa la configuración de la propia aplicación dentro del contenedor.

Prueba de validación: `python -B -m unittest discover -s tests -p test_onboarding.py`.
La prueba de integración está en la suite PostgreSQL efímera existente.
