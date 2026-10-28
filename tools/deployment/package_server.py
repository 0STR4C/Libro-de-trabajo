"""Create a server source ZIP from a Git inventory supplied on stdin. Docker only."""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT_FILES = {
    'Dockerfile', 'compose.yaml', 'compose.production.yaml', '.dockerignore',
    '.gitignore', '.gitattributes', 'requirements.txt', 'package.json',
    'package-lock.json', 'vite.config.js', 'tailwind.config.js', 'postcss.config.js',
    'README.md', 'ARCHITECTURE.md', 'AGENTS.md', 'CLAUDE.md', 'CHANGELOG.md',
    'docs/NAVEGACION_URL.md',
}
SOURCE_DIRS = {'app', 'frontend', 'tools', 'tests', 'legacy_archive'}
EXCLUDED_PARTS = {'node_modules', '__pycache__', '.git', 'bin', 'obj', 'dist', 'dist-libro'}
PRIVATE_PARTS = {'artifacts', 'backups', 'postgres-backups', 'private', 'secrets', 'data-input'}
PRIVATE_SUFFIXES = {'.env', '.db', '.sqlite', '.sqlite3', '.dump', '.log', '.pyc',
                    '.pem', '.key', '.p12', '.pfx', '.crt', '.cer', '.zip',
                    '.bak', '.backup', '.tar', '.gz', '.sql', '.csv', '.tsv',
                    '.xlsx', '.xls'}
RUNTIME_SUFFIXES = {'.py', '.jsx', '.js', '.css', '.html', '.json', '.svg', '.ico', '.png'}
DEPLOYMENT_PROFILE = 'sistemas-20260925'


def check_deployment_profile(root):
    """Fail closed if the accepted deployment settings disappear from a release."""
    base = (root / 'compose.yaml').read_text(encoding='utf-8')
    production = (root / 'compose.production.yaml').read_text(encoding='utf-8')
    example = (root / 'tools/deployment/server.env.example').read_text(encoding='utf-8')
    required = {
        'puerto configurable en ambos Compose': all('${APP_PORT:-8000}:8000' in text for text in (base, production)),
        'rotación de logs': all(text in production for text in ('json-file', 'max-size: "10m"', 'max-file: "3"')),
        'init y privilegios de app': 'init: true' in production and 'no-new-privileges:true' in production,
        'margen inicial de salud': 'start_period: 60s' in production,
        'identidad del proyecto': 'COMPOSE_PROJECT_NAME=libro-trabajo' in example,
        'plantilla de puerto y backup': 'APP_PORT=8000' in example and 'BACKUP_MAX_AGE_SECONDS=5400' in example,
        'plantilla sin secretos': all(re.search(rf'(?m)^{key}=[ \t]*$', example) for key in ('POSTGRES_PASSWORD', 'APP_SECRET', 'ADMIN_PASSWORD')),
    }
    missing = [name for name, valid in required.items() if not valid]
    if missing:
        raise ValueError('Contrato de Sistemas incumplido: ' + ', '.join(missing))


def allowed(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not p.parts or '\\' in name:
        return False
    if any(part.lower() in EXCLUDED_PARTS | PRIVATE_PARTS for part in p.parts):
        return False
    if name == 'tools/deployment/server.env.example':
        return True
    if p.name.lower().startswith('.env') or any(suffix.lower() in PRIVATE_SUFFIXES for suffix in p.suffixes):
        return False
    return name in ROOT_FILES or p.parts[0] in SOURCE_DIRS


def missing_runtime_sources(root, inventory):
    """Fail closed on unpublished application modules, without examining their contents."""
    missing = []
    for directory in ('app', 'frontend'):
        for path in (root / directory).rglob('*'):
            if path.is_symlink():
                raise ValueError(f'Enlace simbólico en código de aplicación: {path.relative_to(root)}')
            if not path.is_file():
                continue
            name = path.relative_to(root).as_posix()
            if allowed(name) and path.suffix.lower() in RUNTIME_SUFFIXES and name not in inventory:
                missing.append(name)
    return sorted(missing)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--include', action='append', default=[], metavar='RUTA',
                        help='Fuente local adicional explícita, relativa al proyecto')
    parser.add_argument('--changed-path', action='append', default=[], metavar='RUTA',
                        help='Ruta con cambios locales para identificar el estado del paquete')
    args = parser.parse_args()
    root = args.root.resolve()
    check_deployment_profile(root)
    tracked = {line.strip().replace('\\', '/') for line in sys.stdin if line.strip()}
    explicit = set(args.include)
    names = sorted(tracked | explicit)
    # Packaging support must be included even before these new files are committed.
    names = sorted(set(names) | {'frontend/routes.js', 'docs/NAVEGACION_URL.md'} | {
        str(path.relative_to(root)).replace('\\', '/')
        for path in (root / 'tools/deployment').iterdir()
        if path.is_file() and (path.suffix in {'.py', '.ps1', '.md', '.txt'} or path.name == 'server.env.example')
    })
    omitted = missing_runtime_sources(root, set(names))
    if omitted:
        raise ValueError('Fuentes de aplicación fuera del inventario; incluir explícitamente '
                         'con --include RUTA o incorporarlas a Git: ' + ', '.join(omitted))
    sources = []
    for name in names:
        if name in explicit and not allowed(name):
            raise ValueError(f'Fuente adicional no permitida: {name}')
        if not allowed(name):
            continue
        source = root / name
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError(f'Ruta no permitida: {name}')
        if not source.is_file():
            raise FileNotFoundError(name)
        sources.append((name, source))
    required = {'Dockerfile', 'compose.yaml', 'compose.production.yaml', 'package-lock.json',
                'app/static/frontend/prime-react.js', 'frontend/main.jsx', 'frontend/routes.js',
                'docs/NAVEGACION_URL.md',
                'tools/postgres_backup/backup.sh', 'tools/postgres_backup/backup_health.sh'}
    if not required.issubset({name for name, _ in sources}):
        raise ValueError('Faltan archivos necesarios para construir o ejecutar el servidor')
    if any(name not in {item for item, _ in sources} for name in args.changed_path):
        raise ValueError('Una ruta declarada como modificada no está en el paquete')
    output = args.output
    if output.exists() or output.with_suffix('.zip.sha256').exists():
        raise FileExistsError('Usar un nombre nuevo; no se sobrescriben entregas')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {}
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, source in sources:
            content = source.read_bytes()
            if source.suffix == '.sh':
                content = content.replace(b'\r\n', b'\n')
            archive.writestr(name, content)
            manifest[name] = hashlib.sha256(content).hexdigest()
        generated = {
            'data/wfm/README.md': b'Carpeta de precargas opcionales. No contiene datos operativos.\n',
            '.env.example': (root / 'tools/deployment/server.env.example').read_bytes(),
            'INSTALACION_SERVIDOR.md': (root / 'tools/deployment/SERVER_INSTALL.md').read_bytes(),
        }
        for name, content in generated.items():
            archive.writestr(name, content)
            manifest[name] = hashlib.sha256(content).hexdigest()
        source_digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        archive.writestr('PACKAGE_MANIFEST.json', json.dumps({
            'base_revision': args.revision,
            'source_state': 'modified_working_tree' if args.changed_path or explicit else 'working_tree_unverified',
            'changed_paths': sorted(set(args.changed_path) | explicit),
            'explicit_sources': sorted(explicit),
            'source_snapshot_sha256': source_digest,
            'contents': 'Working tree source; no operational data or images',
            'deployment_profile': DEPLOYMENT_PROFILE,
            'sha256': manifest,
        }, indent=2))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP corrupto')
        for name, expected in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f'Hash incorrecto: {name}')
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(f'{checksum}  {output.name}\n', encoding='utf-8')
    print(json.dumps({'archive': str(output), 'files': len(manifest) + 1,
                      'bytes': output.stat().st_size, 'sha256': checksum, 'integrity': 'OK'}))


if __name__ == '__main__':
    main()
