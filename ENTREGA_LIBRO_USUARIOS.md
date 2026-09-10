# Entrega Libro de Trabajo y usuarios — 8/9/2026

## Resultado comprobado

- 39 cuentas nuevas, activas, con rol Telefonista. Ninguna coincidencia previa.
- Segunda comprobación: 39 existentes, cero pendientes; no se duplicaron cuentas.
- Contraseña aleatoria temporal común generada dentro del proceso: no se mostró
  ni se guardó en archivos. Cada cuenta conserva hash con sal independiente.
- Administrador ya podía editar nombre, correo, rol, estado y contraseña; se
  verificó su restablecimiento mediante API en PostgreSQL temporal, sin cambiar
  ninguna contraseña existente en la base operativa.
- Nombre visible Libro de Trabajo, logo SVG, favicon ICO y nuevo EXE con icono.
- Aplicación local actualizada y `/health` responde `ok`.
- SQLite histórica intacta (SHA-256):
  `820BB8ACB27A63008F572D61896ED91E6FAC597A9CFE035C36C86F8689D4148C`.

## Archivos creados

- `app/static/libro-trabajo.svg`, `libro-trabajo.ico`, `branding.js`.
- `tools/branding/`: `build-icon.ps1`, `create-project-shortcut.ps1`,
  `test-branding.cjs`, `package.json`, `README.md`.
- `tools/user_onboarding/`: `import_users.py`, `README.md`.
- `data/onboarding/telefonistas-20260908.json`: datos personales de entrada,
  separados de las herramientas. No contiene contraseñas.
- `tests/test_onboarding.py`.
- `tools/desktop_launcher/dist-libro/`: EXE, DLL y archivos .NET asociados.
- `Libro de Trabajo.lnk`: acceso directo dentro del proyecto, no en el Escritorio.
- `ENTREGA_LIBRO_USUARIOS.md`.
- Residuos de compilación/comprobación conservados en `.build/` y directorios
  `bin/obj` del lanzador. `.build/libro-trabajo-preview.png` es la revisión visual.

## Archivos modificados

- `app/static/index.html`: carga de identidad.
- `app/local_server.py`: versión 1.15.0 y notas.
- `tools/desktop_launcher/Program.cs`, `CentroOperativoLauncher.csproj`, `README.md`.
- `tools/wfm_offline_build/Dockerfile`: incorpora la herramienta de alta a la
  imagen candidata sin reinstalar dependencias.
- `tests/test_postgres_security.py`: idempotencia y restablecimiento por Admin.
- `README.md`, `CHANGELOG.md`.

No se modificó la nota para continuar en otra PC ni se eliminó el EXE anterior.

## Comandos y pruebas

- `python -B -m unittest discover -s tests -q`: 48 pruebas; 38 ejecutadas y
  10 omitidas por entorno. Nueve PostgreSQL se ejecutaron aparte, todas aprobadas.
- `tools/postgres_security_test/run.ps1 -ImageName centro-libro-candidate:latest`:
  base efímera, sin volumen operativo.
- `dotnet publish tools/desktop_launcher/CentroOperativoLauncher.csproj -c Release --no-restore -p:AssemblyName=LibroDeTrabajo -o tools/desktop_launcher/dist-libro`.
- `tools/desktop_launcher/test-launcher.ps1`: guardas del lanzador aprobadas;
  extracción del icono del EXE validada con System.Drawing.
- `node tools/branding/test-branding.cjs`: navegador temporal sin autenticación,
  destinos externos bloqueados; título, logo, login y favicon verificados.
- Se construyó la candidata reutilizando dependencias locales, se conservó la
  imagen anterior como `centro-operativo:pre-libro-20260908` y se reinició solo app.
- Se ejecutó `python -m tools.user_onboarding.import_users` dentro de app con el
  listado por stdin: primero comprobación, luego `--apply`, después comprobación.

## Reutilización y pendiente del Administrador

Generador: `powershell -File tools/branding/build-icon.ps1` (rechaza sobrescribir).
Alta: instrucciones completas en `tools/user_onboarding/README.md`; no incluir
datos personales ni contraseñas en el código de esa herramienta.
Antes de entregar accesos: asignar roles definitivos y establecer contraseñas en
Configuración → Usuarios → Editar. No es necesario conocer la temporal generada.
