"""Pruebas de empaquetado con fuentes ficticias; nunca leen datos operativos."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tools.deployment.package_server import allowed, missing_runtime_sources


PACKAGE = Path(__file__).resolve().parents[1] / 'tools' / 'deployment' / 'package_server.py'
VALIDATE = PACKAGE.with_name('validate_compose.py')


class DeploymentContractTests(unittest.TestCase):
    def test_sensitive_names_and_paths_are_rejected(self):
        for name in ('app/config.env', 'app/.env.local', 'tools/private/key.txt',
                     'app/static/key.pem', 'app/static/cert.p12', 'app/data.db',
                     'app/backup.dump', 'app/backup.dump.sha256',
                     'app/input.csv', 'app/../outside.py', '/absolute.py',
                     'artifacts/result.zip'):
            with self.subTest(name=name):
                self.assertFalse(allowed(name))
        self.assertTrue(allowed('tools/deployment/server.env.example'))
        self.assertTrue(allowed('app/normal.py'))

    def test_missing_runtime_sources_are_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'app').mkdir()
            (root / 'frontend').mkdir()
            (root / 'app' / 'new_module.py').write_text('VALUE = 1\n')
            (root / 'frontend' / 'new_view.jsx').write_text('export default 1;\n')
            (root / 'app' / 'config.env').write_text('FICTITIOUS=1\n')
            self.assertEqual(missing_runtime_sources(root, set()),
                             ['app/new_module.py', 'frontend/new_view.jsx'])

    def test_package_is_self_contained_and_traced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {
                'Dockerfile': 'FROM scratch\n', 'compose.yaml': '${APP_PORT:-8000}:8000\n',
                'compose.production.yaml': '${APP_PORT:-8000}:8000\njson-file\nmax-size: "10m"\nmax-file: "3"\ninit: true\nno-new-privileges:true\nstart_period: 60s\n',
                'package-lock.json': '{}', 'frontend/main.jsx': 'export default 1;',
                'frontend/routes.js': 'export const routes = [];',
                'docs/NAVEGACION_URL.md': '# Rutas\n',
                'app/static/frontend/prime-react.js': 'console.log(1);',
                'app/new_module.py': 'VALUE = 1\n',
                'tools/postgres_backup/backup.sh': '#!/bin/sh\n',
                'tools/postgres_backup/backup_health.sh': '#!/bin/sh\n',
                'tools/deployment/SERVER_INSTALL.md': 'Instalación ficticia',
                'tools/deployment/server.env.example':
                    'COMPOSE_PROJECT_NAME=libro-trabajo\nAPP_PORT=8000\nBACKUP_MAX_AGE_SECONDS=5400\nPOSTGRES_PASSWORD=\nAPP_SECRET=\nADMIN_PASSWORD=\n',
            }
            for name, content in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding='utf-8')
            inventory = '\n'.join(name for name in files if name != 'app/new_module.py') + '\n'
            output = root / 'release.zip'
            command = [sys.executable, str(PACKAGE), '--root', str(root),
                       '--output', str(output), '--revision', 'fixture123']
            missing = subprocess.run(command, input=inventory, text=True, capture_output=True)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn('app/new_module.py', missing.stderr)
            complete = subprocess.run(command + ['--include', 'app/new_module.py'],
                                      input=inventory, text=True, capture_output=True)
            self.assertEqual(complete.returncode, 0, complete.stderr)
            with zipfile.ZipFile(output) as archive:
                manifest = json.loads(archive.read('PACKAGE_MANIFEST.json'))
                self.assertEqual(manifest['source_state'], 'modified_working_tree')
                self.assertEqual(manifest['explicit_sources'], ['app/new_module.py'])
                self.assertEqual(archive.read('app/new_module.py'), b'VALUE = 1\n')
                self.assertEqual(archive.read('frontend/routes.js'), b'export const routes = [];')
                self.assertEqual(archive.read('docs/NAVEGACION_URL.md'), b'# Rutas\n')
                for name, expected in manifest['sha256'].items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), expected)

    def test_effective_compose_accepts_optional_worker_and_alternate_port(self):
        base = {
            'name': 'libro-trabajo', 'volumes': {'postgres_data': {'name': 'libro-trabajo_postgres_data'}},
            'services': {
                'app': {'ports': [{'published': '8000', 'target': 8000, 'host_ip': '127.0.0.1'}],
                        'logging': self.logging(), 'init': True,
                        'security_opt': ['no-new-privileges:true'],
                        'healthcheck': {'start_period': '1m0s'}},
                'db': {'logging': self.logging(), 'ports': []},
                'backup': {'logging': self.logging()},
            },
        }
        for with_worker in (False, True):
            for port in ('8000', '18099'):
                config = json.loads(json.dumps(base))
                config['services']['app']['ports'][0]['published'] = port
                if with_worker:
                    config['services']['delay-review-worker'] = {
                        'logging': self.logging(), 'init': True,
                        'security_opt': ['no-new-privileges:true']}
                outcome = subprocess.run([sys.executable, str(VALIDATE), port],
                                         input=json.dumps(config), text=True, capture_output=True)
                self.assertEqual(outcome.returncode, 0, outcome.stderr)
                config['services']['app']['logging']['options']['max-file'] = '99'
                invalid = subprocess.run([sys.executable, str(VALIDATE), port],
                                         input=json.dumps(config), text=True, capture_output=True)
                self.assertNotEqual(invalid.returncode, 0)

    @staticmethod
    def logging():
        return {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '3'}}


if __name__ == '__main__':
    unittest.main()
