# Identidad Libro de Trabajo

Icono vectorial original: `app/static/libro-trabajo.svg`. La variante ICO incluye
16, 24, 32, 48, 64, 128 y 256 px para navegador y ejecutable Windows.

Requisitos: PowerShell en Windows y System.Drawing incluido en .NET; no instala
dependencias ni utiliza servicios externos.

Desde la raíz: `powershell -File tools/branding/build-icon.ps1`.
Entrada: geometría del libro definida en el script. Salida exclusiva:
`app/static/libro-trabajo.ico`. Rechaza sobrescribir un icono existente.
El SVG y el script son la fuente reutilizable; el ICO queda conservado.

Comprobación: el ejecutable compilado debe devolver un icono no nulo mediante
`System.Drawing.Icon.ExtractAssociatedIcon(rutaExe)`.

## Acceso fácil dentro del proyecto

`powershell -File tools/branding/create-project-shortcut.ps1` crea
`Libro de Trabajo.lnk` en la raíz y apunta al EXE compilado de `dist-libro`.
Requiere WScript.Shell de Windows. No cambia el Escritorio, Inicio, Registro ni
configuración del sistema y rechaza reemplazar un acceso directo existente.

## Comprobación visual local

`node tools/branding/test-branding.cjs`, desde la raíz del proyecto.
Requiere Node, Playwright 1.62.1 (runtime disponible, sin instalar paquetes)
y Edge. Solo visita `http://127.0.0.1:8000/`, bloquea destinos externos y no
inicia sesión ni usa el perfil del usuario. Valida título, login, SVG y favicon;
genera `.build/libro-trabajo-preview.png`. Puede requerir `NODE_PATH` apuntando
a los paquetes del runtime. La imagen de comprobación no es la fuente del logo.
