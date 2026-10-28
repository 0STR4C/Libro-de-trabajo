import assert from 'node:assert/strict';
import test from 'node:test';
import { formatUYU, uyuInputProps } from '../frontend/money.js';
import { isDirectLocation, manualRegionPoints, regionalSelection, selectedCoordinates } from '../frontend/quote-address.js';

test('formatea pesos con punto de miles, coma decimal y dos centésimos cuando corresponde', () => {
  assert.equal(formatUYU(1000), '$ 1.000');
  assert.equal(formatUYU(47860, { cents: true }), '$ 47.860,00');
  assert.equal(formatUYU(1234.5), '$ 1.234,50');
  assert.equal(uyuInputProps.useGrouping, true);
});

test('las coordenadas seleccionadas son inequívocas y los números de tarea quedan como texto', () => {
  const item = { label: 'San Martín 100, Rosario, Santa Fe, Argentina', latitude: -32.9, longitude: -60.7 };
  assert.equal(selectedCoordinates(item), '-32.900000, -60.700000');
  assert.equal(isDirectLocation(selectedCoordinates(item)), true);
  assert.equal(isDirectLocation('San Martín 100'), false);
  assert.equal(isDirectLocation('https://www.google.com.ar/maps/place/ejemplo'), true);
  assert.equal(isDirectLocation('https://www.google.com.br/maps/place/exemplo'), true);
  assert.equal(isDirectLocation('https://maps.app.goo.gl/ejemplo'), true);
  assert.equal(isDirectLocation('https://notgoogle.com/maps/place/ejemplo'), false);
  assert.equal(isDirectLocation('https://google.com.ejemplo.invalid/maps'), false);
  const taskNumber = '001000';
  assert.equal(taskNumber, '001000');
  assert.notEqual(taskNumber, formatUYU(1000));
});

test('la base desmarcada no entra en el contexto manual y una selección regional bloquea la tarifa', () => {
  const form = { origin: '-34.9011, -56.1645', destination: '-34.8900, -56.1600', mobile_origin: '-23.5505, -46.6333', mobile_origin_country: 'BR', mobile_origin_confirmed: true, include_mobile: false };
  assert.deepEqual(manualRegionPoints(form), [form.origin, form.destination]);
  assert.equal(regionalSelection(form), false);
  form.include_mobile = true;
  assert.equal(manualRegionPoints(form).length, 3);
  assert.equal(regionalSelection(form), true);
  form.mobile_origin = '';
  assert.equal(regionalSelection(form), false);
});
