import assert from 'node:assert/strict';
import test from 'node:test';
import { createWfmRequestCoordinator, wfmResponseMatches } from '../frontend/wfm-request-coordinator.js';

test('una carga tardía del día A no sustituye el día B ni otro equipo', () => {
  const guard = createWfmRequestCoordinator({ day: '2026-10-12', team: 'Telefonista', revision: 4 });
  const dayA = guard.beginLoad('2026-10-13', 'Telefonista');
  const dayB = guard.beginLoad('2026-10-14', 'Planificador');

  assert.equal(guard.isLoadCurrent(dayA), false);
  assert.equal(guard.acceptLoad(dayA, 8), false);
  assert.equal(guard.acceptLoad(dayB, 2), true);
  assert.deepEqual(
    { day: guard.context.day, team: guard.context.team, revision: guard.context.revision },
    { day: '2026-10-14', team: 'Planificador', revision: 2 },
  );
});

test('guardar A y navegar a B deja la respuesta de A asociada a A', () => {
  const guard = createWfmRequestCoordinator({ day: '2026-10-12', team: 'Telefonista', revision: 4 });
  const saveA = guard.beginMutation('save');
  const loadB = guard.beginLoad('2026-10-13', 'Telefonista');

  assert.equal(guard.isMutationCurrent(saveA), false);
  assert.equal(guard.acceptMutation(saveA, 5), false);
  assert.equal(guard.acceptLoad(loadB, 1), true);
  assert.equal(guard.context.day, '2026-10-13');
  assert.equal(wfmResponseMatches({ plan_date: '2026-10-12', team: 'Telefonista' }, saveA), true);
  assert.equal(wfmResponseMatches({ plan_date: '2026-10-12', team: 'Planificador' }, saveA), false);
});

test('doble clic y acciones consecutivas comparten una única mutación pendiente', () => {
  const guard = createWfmRequestCoordinator({ day: '2026-10-12', team: 'Telefonista', revision: 4 });
  const first = guard.beginMutation('save');
  assert.ok(first);
  assert.equal(guard.beginMutation('save'), null);
  assert.equal(guard.beginMutation('optimize'), null);
  assert.equal(guard.beginMutation('publish'), null);
  assert.equal(guard.beginMutation('publish-week'), null);

  guard.finishMutation(first);
  const next = guard.beginMutation('publish');
  assert.ok(next);
  guard.markEdited();
  assert.equal(guard.acceptMutation(next, 5), false, 'una edición local durante el POST no puede ser reemplazada');
});
