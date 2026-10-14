import assert from 'node:assert/strict';
import test from 'node:test';
import { createArrivalPageRequests } from '../frontend/arrival-times-requests.js';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test('una recuperación antigua no reemplaza la página ni el filtro nuevos', async () => {
  const requests = createArrivalPageRequests();
  const recovery = deferred();
  const navigation = deferred();
  const accepted = [];
  const options = { isActive: () => true, accept: page => accepted.push(page), reject: error => { throw error; }, finish: () => {} };
  const old = requests.load(() => recovery.promise, options);
  const latest = requests.load(() => navigation.promise, options);
  navigation.resolve({ offset: 50, filter: 'MONTEVIDEO' });
  assert.equal(await latest, true);
  recovery.resolve({ offset: 0, filter: 'CANELONES' });
  assert.equal(await old, false);
  assert.deepEqual(accepted, [{ offset: 50, filter: 'MONTEVIDEO' }]);
});

test('salir del módulo invalida respuestas y errores tardíos', async () => {
  const requests = createArrivalPageRequests();
  const pending = deferred();
  let active = true;
  const accepted = [];
  const errors = [];
  const result = requests.load(() => pending.promise, {
    isActive: () => active, accept: page => accepted.push(page), reject: error => errors.push(error), finish: () => {},
  });
  active = false;
  requests.invalidate();
  pending.resolve({ offset: 0 });
  assert.equal(await result, false);
  assert.deepEqual(accepted, []);
  assert.deepEqual(errors, []);
});

test('un cambio de filtro invalida una recuperación pendiente aunque la API responda después', async () => {
  const requests = createArrivalPageRequests();
  const recovery = deferred();
  const accepted = [];
  const old = requests.load(() => recovery.promise, {
    isActive: () => true, accept: page => accepted.push(page), reject: error => { throw error; }, finish: () => {},
  });
  requests.invalidate();
  recovery.resolve({ offset: 0, filter: 'anterior' });
  assert.equal(await old, false);
  assert.deepEqual(accepted, []);
});
