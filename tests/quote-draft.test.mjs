import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeQuoteDraft } from '../frontend/quote-draft.js';

test('un borrador parcial conserva los datos válidos y completa los faltantes', () => {
  const draft = normalizeQuoteDraft({ mode: 'manual', coverage: 'uninsured', manual_trip_km: 12.5, include_mobile: true });
  assert.equal(draft.mode, 'manual');
  assert.equal(draft.coverage, 'uninsured');
  assert.equal(draft.manual_trip_km, 12.5);
  assert.equal(draft.destination, '');
  assert.equal(draft.manual_mobile_km, null);
});

test('un borrador dañado no introduce campos extra ni valores incompatibles', () => {
  assert.equal(normalizeQuoteDraft([]), null);
  assert.equal(normalizeQuoteDraft('corrupto'), null);
  const draft = normalizeQuoteDraft({ mode: 'otro', origin: 123, manual_trip_km: -1, coverage: 'admin', special: true, gavilan: true, token: 'secreto' });
  assert.equal(draft.mode, 'automatic');
  assert.equal(draft.origin, '');
  assert.equal(draft.manual_trip_km, null);
  assert.equal(draft.coverage, 'insured');
  assert.equal(draft.special, true);
  assert.equal(draft.gavilan, false);
  assert.equal(Object.hasOwn(draft, 'token'), false);
});

test('un borrador anterior conserva coordenadas y exige reconfirmarlas', () => {
  const draft = normalizeQuoteDraft({ origin: '-34.901100, -56.164500', destination: 'Avenida Italia 1234' });
  assert.equal(draft.origin, '-34.901100, -56.164500');
  assert.equal(draft.origin_entry_mode, 'coordinates');
  assert.equal(draft.origin_confirmed, false);
  assert.equal(draft.destination_entry_mode, 'address');
});
