import test from 'node:test';
import assert from 'node:assert/strict';
import { REQUEST_TIMEOUT_MS, requestDeadline, requestTimeoutError } from '../frontend/request-deadline.js';

test('una solicitud pendiente termina al alcanzar el plazo configurado', async () => {
  const controller = new AbortController();
  const deadline = requestDeadline(controller, 10);
  await new Promise(resolve => controller.signal.addEventListener('abort', resolve, { once: true }));
  assert.equal(deadline.expired(), true);
  assert.equal(controller.signal.aborted, true);
  deadline.clear();
});

test('una respuesta terminada libera el temporizador', async () => {
  const controller = new AbortController();
  const deadline = requestDeadline(controller, 10);
  deadline.clear();
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal(deadline.expired(), false);
  assert.equal(controller.signal.aborted, false);
});

test('el vencimiento de una escritura nunca afirma que se perdió el guardado', () => {
  assert.equal(REQUEST_TIMEOUT_MS, 30_000);
  assert.equal(requestTimeoutError(true).uncertain, true);
  assert.equal(requestTimeoutError(false).uncertain, false);
});
