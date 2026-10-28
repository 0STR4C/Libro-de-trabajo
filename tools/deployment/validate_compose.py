"""Validate rendered production Compose JSON from synthetic settings on stdin."""
import json
import sys

config = json.load(sys.stdin)
services = config['services']
ports = services['app'].get('ports', [])
expected_port = sys.argv[1] if len(sys.argv) > 1 else '8000'
checks = {
    'puerto único configurable': len(ports) == 1 and str(ports[0]['published']) == expected_port and ports[0]['target'] == 8000,
    'loopback': len(ports) == 1 and ports[0]['host_ip'] == '127.0.0.1',
    'base no publicada': not services['db'].get('ports'),
    'logs limitados': all(
        service.get('logging') == {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '3'}}
        for name, service in services.items() if name in ('app', 'db', 'backup', 'delay-review-worker')
    ),
    'servicios esenciales': all(name in services for name in ('app', 'db', 'backup')),
    'init': services['app'].get('init') is True,
    'privilegios': 'no-new-privileges:true' in services['app'].get('security_opt', []),
    'worker restringido': 'delay-review-worker' not in services or (
        services['delay-review-worker'].get('init') is True
        and 'no-new-privileges:true' in services['delay-review-worker'].get('security_opt', [])
    ),
    'margen de salud': services['app']['healthcheck'].get('start_period') == '1m0s',
    'proyecto estable': config['name'] == 'libro-trabajo',
    'volumen estable': config['volumes']['postgres_data']['name'] == 'libro-trabajo_postgres_data',
}
failures = [name for name, result in checks.items() if not result]
if failures:
    raise SystemExit('Fallo de contrato: ' + ', '.join(failures))
print('OK: contrato de producción, puerto ' + expected_port)
