import test from 'node:test';
import assert from 'node:assert/strict';
import { delayGuidance, matchingExceptions } from '../frontend/delay-guidance.js';
import { affectedViews } from '../frontend/operational-invalidation.js';

const exceptions = [
  { id: 1, service: 'TODAS', zone: 'Todo el departamento', message: 'No confirmar tiempos' },
  { id: 2, service: 'ML', zone: 'Pocitos', message: 'Margen de', minutes: 25 },
  { id: 3, service: 'GRÚA', zone: 'Pocitos', message: 'A confirmar' },
];

test('el alcance general y la prestación concreta coinciden sin escoger un registro arbitrario', () => {
  assert.deepEqual(matchingExceptions(exceptions, 'ML', 'Pocitos').map(item => item.id), [1, 2]);
  assert.deepEqual(matchingExceptions(exceptions, 'GRÚA', 'Pocitos').map(item => item.id), [1, 3]);
  assert.deepEqual(matchingExceptions(exceptions.slice(1), 'ML', 'Buceo'), []);
  assert.deepEqual(matchingExceptions(exceptions.slice(1), 'ML', 'Todo el departamento'), []);
});

test('un margen no se convierte en tiempo total y una revisión vencida oculta sus minutos', () => {
  assert.match(delayGuidance(exceptions[1]), /no equivale al tiempo total/i);
  assert.doesNotMatch(delayGuidance({ ...exceptions[1], needs_review: true }), /25/);
  assert.equal(delayGuidance({ ...exceptions[0], needs_review: true }), 'No confirmar tiempos. Verificar antes de comunicar.');
});

test('máximo, intervalo, texto y restricción de servicio conservan su significado', () => {
  assert.equal(delayGuidance({ message: 'Máximo de', minutes: 90 }), 'Máximo informado: 90 min.');
  assert.equal(delayGuidance({ message: 'Intervalo estimado', minutes_min: 60, minutes_max: 90 }), 'Entre 60 y 90 min estimados.');
  assert.doesNotMatch(delayGuidance({ message: 'Intervalo estimado', minutes_min: 60, minutes_max: 90, needs_review: true }), /60|90/);
  assert.equal(delayGuidance({ message: 'Otra indicación', instruction_text: 'Informar posible demora en ruta' }), 'Informar posible demora en ruta');
  assert.equal(delayGuidance({ message: 'No confirmar tiempos' }), 'No confirmar tiempos');
  assert.equal(delayGuidance({ message: 'No generar servicio' }), 'No generar servicio');
  assert.deepEqual(matchingExceptions([{ id: 7, service: 'GRÚA', zone: 'Pocitos, Buceo' }], 'ML', 'Pocitos'), []);
  assert.deepEqual(matchingExceptions([{ id: 7, service: 'GRÚA', zone: 'Pocitos, Buceo' }], 'GRÚA', 'Buceo').map(item => item.id), [7]);
});

test('alta, verificación y normalización invalidan Resumen sin recargar la página', () => {
  for (const path of ['/api/delays', '/api/delays/4/verify', '/api/delays/4/normalize']) {
    assert.ok(affectedViews(path).includes('dashboard'));
  }
});
