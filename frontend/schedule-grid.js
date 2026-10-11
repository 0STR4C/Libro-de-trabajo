// Índices de lectura: una persona puede tener varios registros válidos en un día.
export const scheduleDay = value => value instanceof Date
  ? `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
  : /^\d{4}-\d{2}-\d{2}/.test(String(value || '')) ? String(value).slice(0, 10) : '';

export function shiftScheduleDay(value, offset) {
  const current = new Date(`${scheduleDay(value)}T12:00:00`);
  current.setDate(current.getDate() + offset);
  return scheduleDay(current);
}

export function indexSchedules(rows) {
  const byPersonDay = new Map();
  const byDay = new Map();
  const peopleWithRows = new Set();
  const add = (row, day, continuation) => {
    const key = `${row.user_id}:${day}`;
    const entry = { row, continuation };
    if (!byPersonDay.has(key)) byPersonDay.set(key, []);
    if (!byDay.has(day)) byDay.set(day, []);
    byPersonDay.get(key).push(entry);
    byDay.get(day).push(entry);
  };
  for (const row of rows) {
    const day = scheduleDay(row.schedule_date);
    if (!day) continue;
    peopleWithRows.add(Number(row.user_id));
    add(row, day, false);
    if (Number(row.end_slot) > 48) add(row, shiftScheduleDay(day, 1), true);
  }
  return { byPersonDay, byDay, peopleWithRows };
}

export function schedulePeople(people, rows) {
  const result = new Map(people.map(person => [Number(person.id), person]));
  for (const row of rows) {
    const id = Number(row.user_id);
    if (!result.has(id)) result.set(id, {
      id: row.user_id, display_name: row.display_name, role_name: row.role_name
    });
  }
  return [...result.values()];
}

export function createScheduleResponseGate(initialKey) {
  let sequence = 0;
  let key = initialKey;
  return {
    begin(nextKey) { key = nextKey; return ++sequence; },
    accepts(ticket) { return ticket === sequence; },
    matches(nextKey) { return nextKey === key; },
    invalidate() { sequence += 1; }
  };
}
