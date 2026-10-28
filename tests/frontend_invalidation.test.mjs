import test from 'node:test';
import assert from 'node:assert/strict';
import { affectedViews } from '../frontend/operational-invalidation.js';

test('una demora actualiza resumen y auditoría al volver, sin invalidar formularios ajenos', () => {
  assert.deepEqual(affectedViews('/api/delays/17/normalize'), ['dashboard', 'delayAudit', 'supervision']);
  assert.equal(affectedViews('/api/delays/17/normalize').includes('notices'), false);
});

test('un aviso solo invalida los indicadores que lo consumen', () => {
  assert.deepEqual(affectedViews('/api/notices/4/status'), ['supervision']);
});

test('otras consultas no desencadenan recargas de vistas', () => {
  assert.deepEqual(affectedViews('/api/reports/notices.csv'), []);
});
