import test from 'node:test';
import assert from 'node:assert/strict';
import { departmentAt, isDelayReviewDue, nextReviewDeadline } from '../frontend/delay-map-state.js';

const start = Date.parse('2026-10-11T12:00:00Z');
const pending = { id: 1, zone: 'Piriápolis', review_due_at: '2026-10-11T12:01:00Z', needs_review: false };

test('un vencimiento cambia la indicación y los contadores sin otra respuesta de red', () => {
  const snapshot = { department: 'MALDONADO', delays: [pending], active_count: 1, verified_count: 1, review_due_count: 0 };
  assert.equal(isDelayReviewDue(pending, start), false);
  assert.equal(nextReviewDeadline({ departments: [snapshot] }, start), start + 60000);
  assert.deepEqual([departmentAt(snapshot, start).verified_count, departmentAt(snapshot, start).review_due_count], [1, 0]);
  assert.equal(isDelayReviewDue(pending, start + 60000), true);
  assert.deepEqual([departmentAt(snapshot, start + 60000).verified_count, departmentAt(snapshot, start + 60000).review_due_count], [0, 1]);
  assert.equal(nextReviewDeadline({ departments: [snapshot] }, start + 60000), null);
});

test('la siguiente lectura normalizada elimina la demora sin alterar el snapshot anterior', () => {
  const previous = { department: 'MALDONADO', delays: [pending] };
  const current = { department: 'MALDONADO', delays: [] };
  assert.equal(departmentAt(previous, start).active_count, 1);
  assert.equal(departmentAt(current, start).active_count, 0);
  assert.equal(previous.delays.length, 1);
});

test('un plazo ausente o inválido nunca se presenta como tiempo confirmado', () => {
  assert.equal(isDelayReviewDue({ needs_review: false }, start), true);
  assert.equal(isDelayReviewDue({ review_due_at: 'basura', needs_review: false }, start), true);
});
