import assert from 'node:assert/strict';
import test from 'node:test';
import { createQuoteRequestGuard } from '../frontend/quote-request-guard.js';

test('un resultado pendiente queda obsoleto al cambiar origen, destino, base, cobertura o modalidad', () => {
  for (const field of ['origin', 'destination', 'mobile_origin', 'coverage', 'mode']) {
    const guard = createQuoteRequestGuard();
    const first = guard.begin(`original-${field}`);
    guard.invalidate();
    assert.equal(guard.isCurrent(first.revision), false, field);
    assert.equal(guard.begin(`cambiado-${field}`).reason, 'pending', field);
    guard.finish();
    const next = guard.begin(`cambiado-${field}`);
    assert.equal(guard.isCurrent(next.revision), true, field);
  }
});

test('clic, Enter y marcador no duplican una escritura pendiente ni la ya enviada', () => {
  const guard = createQuoteRequestGuard();
  guard.begin('mismos-datos');
  assert.equal(guard.begin('mismos-datos').reason, 'pending');
  guard.invalidate(); // movimiento del pin durante el POST
  assert.equal(guard.begin('pin-movido').reason, 'pending');
  guard.finish();
  assert.equal(guard.begin('mismos-datos').reason, 'duplicate');
  assert.ok(guard.begin('pin-movido').revision);
  guard.finish();
  guard.allowNew(); // decisión explícita de generar una nueva cotización idéntica
  assert.ok(guard.begin('pin-movido').revision);
});

test('la respuesta perdida mantiene el bloqueo de duplicados; un 4xx conocido permite corregir', () => {
  const guard = createQuoteRequestGuard();
  guard.begin('intento-guardado');
  guard.finish(); // la respuesta nunca llegó, el servidor pudo guardar
  assert.equal(guard.begin('intento-guardado').reason, 'duplicate');
  guard.allowNew();
  guard.begin('intento-nuevo');
  guard.rejectKnown();
  guard.finish();
  assert.ok(guard.begin('intento-nuevo').revision);
});
