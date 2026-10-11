import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';
import test from 'node:test';
import { createScheduleResponseGate, indexSchedules, schedulePeople, shiftScheduleDay } from '../frontend/schedule-grid.js';

test('el índice conserva el mismo contenido para celdas simples y no pierde registros adicionales', () => {
  const people = Array.from({ length: 300 }, (_, index) => ({ id: index + 1, display_name: `Persona ${index + 1}` }));
  const days = Array.from({ length: 7 }, (_, index) => shiftScheduleDay('2026-12-28', index));
  const rows = people.flatMap(person => days.map((day, index) => ({
    id: `${person.id}:${day}`, user_id: person.id, schedule_date: day,
    start_slot: 16 + index, end_slot: 29 + index,
    segments: [{ start: 16 + index, end: 29 + index }], notes: `Turno ${index}`,
  })));
  const content = row => `${row.segments.map(segment => `${segment.start}-${segment.end}`).join(' · ')} ${row.notes}`;
  const indexed = indexSchedules(rows);
  for (const person of people) for (const day of days) {
    const before = rows.find(row => row.user_id === person.id && row.schedule_date === day);
    const after = indexed.byPersonDay.get(`${person.id}:${day}`);
    assert.deepEqual(after.map(({ row }) => content(row)), [content(before)]);
  }
  const extra = { id: 'split:2', user_id: 1, schedule_date: days[0], start_slot: 36, end_slot: 42,
    segments: [{ start: 36, end: 42 }], notes: 'Segundo registro válido' };
  const withExtra = indexSchedules([...rows, extra]);
  assert.deepEqual(withExtra.byPersonDay.get(`1:${days[0]}`).map(({ row }) => row.id),
    [`1:${days[0]}`, 'split:2']);
  assert.equal(withExtra.byDay.get(days[0]).length, 301);
});

test('cambio de año, turno nocturno, descanso, excepción y personas inactivas', () => {
  assert.equal(shiftScheduleDay('2026-12-28', 6), '2027-01-03');
  assert.equal(shiftScheduleDay('2026-12-28', 7), '2027-01-04');
  assert.equal(shiftScheduleDay('2021-01-04', -1), '2021-01-03');
  const night = { id: 'night', user_id: 81, schedule_date: '2026-12-27', start_slot: 44, end_slot: 60,
    break_slot: 50, break_duration: 1, exceptions: [{ type: 'Reunión', start: 52, end: 53 }] };
  const indexed = indexSchedules([night]);
  assert.equal(indexed.byPersonDay.get('81:2026-12-28')[0].continuation, true);
  assert.equal(indexed.byPersonDay.get('81:2026-12-28')[0].row.break_slot, 50);
  assert.equal(indexed.byPersonDay.get('81:2026-12-28')[0].row.exceptions[0].start, 52);
  assert.deepEqual(schedulePeople([{ id: 1, display_name: 'Activa' }], [night]).map(person => person.id), [1, 81]);
});

test('la respuesta tardía no reemplaza la semana ni los filtros nuevos', async () => {
  const gate = createScheduleResponseGate('week=2026-12-28');
  let resolveOld, resolveNew;
  const old = new Promise(resolve => { resolveOld = resolve; });
  const newer = new Promise(resolve => { resolveNew = resolve; });
  let visible = null;
  const first = gate.begin('week=2026-12-28&role=Telefonista');
  const firstCompletion = old.then(value => { if (gate.accepts(first)) visible = value; });
  const second = gate.begin('week=2027-01-04&role=Planificador');
  const secondCompletion = newer.then(value => { if (gate.accepts(second)) visible = value; });
  resolveNew('2027-01-04 Planificador');
  await secondCompletion;
  resolveOld('2026-12-28 Telefonista');
  await firstCompletion;
  assert.equal(visible, '2027-01-04 Planificador');
  assert.equal(gate.matches('week=2026-12-28&role=Telefonista'), false);
  gate.invalidate();
  assert.equal(gate.accepts(second), false);
});

test('medición reproducible del armado de 2.100 celdas, 100 iteraciones', () => {
  const people = Array.from({ length: 300 }, (_, index) => index + 1);
  const days = Array.from({ length: 7 }, (_, index) => shiftScheduleDay('2026-12-28', index));
  const rows = people.flatMap(user_id => days.map(schedule_date => ({ user_id, schedule_date })));
  let comparisons = 0;
  const before = performance.now();
  for (let iteration = 0; iteration < 100; iteration++) for (const user of people) for (const day of days) {
    rows.find(row => { comparisons += 1; return row.user_id === user && row.schedule_date === day; });
  }
  const oldMs = performance.now() - before;
  const after = performance.now();
  for (let iteration = 0; iteration < 100; iteration++) {
    const indexed = indexSchedules(rows);
    for (const user of people) for (const day of days) assert.equal(indexed.byPersonDay.get(`${user}:${day}`).length, 1);
  }
  const newMs = performance.now() - after;
  assert.equal(comparisons, 220605000);
  console.log(`Horarios: lineal ${oldMs.toFixed(1)} ms; índice ${newMs.toFixed(1)} ms; ${comparisons} comparaciones lineales`);
});
