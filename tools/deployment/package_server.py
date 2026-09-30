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
}
SOURCE_DIRS = {'app', 'frontend', 'tools', 'tests', 'legacy_archive'}
EXCLUDED_PARTS = {'node_modules', '__pycache__', '.git', 'bin', 'obj', 'dist', 'dist-libro'}
DEPLOYMENT_PROFILE = 'sistemas-20260925'


def check_deployment_profile(root):
    """Fail closed if the accepted deployment settings disappear from a release."""
    base = (root / 'compose.yaml').read_text(encoding='utf-8')
    production = (root / 'compose.production.yaml').read_text(encoding='utf-8')
    example = (root / 'tools/deployment/server.env.example').read_text(encoding='utf-8')
    required = {
        'puerto configurable en ambos Compose': all('${APP_PORT:-8000}:8000' in text for text in (base, production)),
        'rotación de logs': all(text in production for text in ('json-file', 'max-size: "10m"', 'max-file: "3"')) and production.count('logging: *production-logging') == 3,
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
    if p.is_absolute() or '..' in p.parts or not p.parts:
        return False
    if any(part in EXCLUDED_PARTS for part in p.parts):
        return False
    if p.name.startswith('.env') or p.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.dump', '.log', '.pyc', '.pem', '.key', '.zip'}:
        return False
    return name in ROOT_FILES or p.parts[0] in SOURCE_DIRS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    check_deployment_profile(root)
    names = sorted({line.strip().replace('\\', '/') for line in sys.stdin if line.strip()})
    # Packaging support must be included even before these new files are committed.
    names = sorted(set(names) | {
        str(path.relative_to(root)).replace('\\', '/')
        for path in (root / 'tools/deployment').iterdir()
        if path.is_file() and (path.suffix in {'.py', '.ps1', '.md', '.txt'} or path.name == 'server.env.example')
    })
    sources = []
    for name in names:
        if not allowed(name):
            continue
        source = root / name
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError(f'Ruta no permitida: {name}')
        if not source.is_file():
            raise FileNotFoundError(name)
        sources.append((name, source))
    required = {'Dockerfile', 'compose.yaml', 'compose.production.yaml', 'package-lock.json',
                'app/static/frontend/prime-react.js', 'frontend/main.jsx',
                'tools/postgres_backup/backup.sh', 'tools/postgres_backup/backup_health.sh'}
    if not required.issubset({name for name, _ in sources}):
        raise ValueError('Faltan archivos necesarios para construir o ejecutar el servidor')
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
        archive.writestr('PACKAGE_MANIFEST.json', json.dumps({
            'base_revision': args.revision, 'contents': 'Working tree source; no operational data or images',
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
