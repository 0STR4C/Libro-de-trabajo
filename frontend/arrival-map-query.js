import { delayGuidance, matchingExceptions } from './delay-guidance.js';

export const ALL_DEPARTMENT = 'Todo el departamento';
const key = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLocaleLowerCase();
const members = item => item.zone_members?.length ? item.zone_members : String(item.zone || '').split(',').map(part => part.trim());

export function arrivalIndicationText(item) {
  if (!item) return 'Sin tiempo estándar configurado';
  if (item.indication_type === 'MAXIMUM') return `Máximo de ${item.minutes_max} minutos`;
  if (item.indication_type === 'INTERVAL') return `Entre ${item.minutes_min} y ${item.minutes_max} minutos`;
  if (item.indication_type === 'TO_CONFIRM') return 'A confirmar';
  return `${item.base_estimated_minutes} minutos habituales`;
}

export function arrivalIndicationCompact(item) {
  if (!item) return 'Sin estándar configurado';
  if (item.indication_type === 'MAXIMUM') return `Máximo de ${item.minutes_max} min`;
  if (item.indication_type === 'INTERVAL') return `Entre ${item.minutes_min} y ${item.minutes_max} min`;
  if (item.indication_type === 'TO_CONFIRM') return 'A confirmar';
  return `${item.base_estimated_minutes} min habituales`;
}

export function arrivalDelayText(item) {
  if (item.message === 'Máximo de' && item.minutes) return `Máximo de ${item.minutes} minutos`;
  if (item.message === 'Intervalo estimado' && item.minutes_min && item.minutes_max)
    return `Entre ${item.minutes_min} y ${item.minutes_max} minutos`;
  if (item.message === 'Margen de' && item.minutes)
    return `Margen de ${item.minutes} minutos; confirmar tiempo total`;
  if (item.message === 'Otra indicación') return item.instruction_text || 'A confirmar con Planificación';
  return item.message || 'A confirmar con Planificación';
}

export function arrivalReference(items, service, zone) {
  const candidates = (items || []).filter(item => key(item.service) === key(service));
  const exact = candidates.filter(item => key(item.zone) === key(zone));
  const grouped = candidates.filter(item => key(item.zone) !== key(ALL_DEPARTMENT) && members(item).some(member => key(member) === key(zone)));
  const department = candidates.filter(item => key(item.zone) === key(ALL_DEPARTMENT));
  const matches = exact.length ? exact : grouped.length ? grouped : department;
  return matches.reduce((latest, item) => !latest || item.id > latest.id ? item : latest, null);
}

export function arrivalZoneDifferences(items, service) {
  const byZone = new Map();
  for (const item of items || []) {
    if (key(item.service) !== key(service) || key(item.zone) === key(ALL_DEPARTMENT)) continue;
    const zoneKey = key(item.zone);
    if (!byZone.has(zoneKey) || item.id > byZone.get(zoneKey).id) byZone.set(zoneKey, item);
  }
  return [...byZone.values()].sort((a, b) => a.zone.localeCompare(b.zone, 'es'));
}

export function arrivalZones(catalogZones, delays) {
  const result = new Map();
  for (const zone of [ALL_DEPARTMENT, ...(catalogZones || [])]) result.set(key(zone), zone);
  for (const delay of delays || []) {
    for (const zone of String(delay.zone || '').split(',')) {
      const label = zone.trim();
      if (label && !result.has(key(label))) result.set(key(label), label);
    }
  }
  return [...result.values()];
}

export function arrivalNeedsZone({ delays, items, service, zone, standard, standardStatus = 'ready' }) {
  if (key(zone) !== key(ALL_DEPARTMENT)) return false;
  const specificDelay = (delays || []).some(item =>
    (key(item.service) === key(service) || key(item.service) === 'todas') && key(item.zone) !== key(ALL_DEPARTMENT));
  if (specificDelay) return true;
  const departmentDelay = matchingExceptions(delays, service, ALL_DEPARTMENT).length > 0;
  return !departmentDelay && standardStatus === 'ready' && arrivalZoneDifferences(items, service)
    .some(item => !standard || arrivalIndicationText(item) !== arrivalIndicationText(standard));
}

export function arrivalSituation({ delays, items, service, zone, mapStatus, standardStatus, standard, requireZone = true }) {
  const matching = matchingExceptions(delays, service, zone);
  if (mapStatus !== 'ready') return { matching, state: 'unverified', label: 'Información no disponible', answer: 'Información no disponible', message: 'No se pudo confirmar si hay afectaciones vigentes. Verificá antes de comunicar un tiempo.' };
  if (requireZone && arrivalNeedsZone({ delays, items, service, zone, standard, standardStatus }))
    return { matching, state: 'select_zone', label: 'Zona necesaria', answer: 'Seleccioná una zona para consultar el tiempo', message: 'La indicación varía según la zona.' };
  // No existe una precedencia entre afectaciones superpuestas: se muestran todas y se pide revisión.
  if (matching.length > 1) return { matching, state: 'overlap', label: 'Afectaciones vigentes superpuestas', answer: 'A confirmar con Planificación', message: 'Hay indicaciones superpuestas. Confirmá cuál comunicar.' };
  if (matching.some(item => item.needs_review)) return { matching, state: 'review', label: 'Afectación vigente · revisión pendiente', answer: 'A confirmar con Planificación', message: delayGuidance(matching[0]) };
  if (matching.length) return { matching, state: 'exception', label: 'Afectación vigente', answer: arrivalDelayText(matching[0]), message: 'La afectación vigente reemplaza al estándar.' };
  if (standardStatus !== 'ready') return { matching, state: 'unverified', label: 'Información no disponible', answer: 'Información no disponible', message: 'No se pudo confirmar el tiempo estándar actual.' };
  if (!standard) return { matching, state: 'missing', label: 'Sin estándar configurado', answer: 'A confirmar con Planificación', message: 'No hay tiempo estándar configurado para esta prestación y ubicación.' };
  if (standard.indication_type === 'TO_CONFIRM') return { matching, state: 'unconfirmed', label: 'Tiempo estándar', answer: 'A confirmar', message: 'La referencia habitual indica A confirmar. No comuniques un tiempo numérico.' };
  return { matching, state: 'habitual', label: 'Tiempo estándar', answer: arrivalIndicationText(standard), message: 'Sin afectación vigente para esta selección.' };
}

export function departmentArrivalRows({ items = [], delays = [], service, mapStatus = 'ready', standardStatus = 'ready' }) {
  const relevant = items.filter(item => key(item.service) === key(service));
  const relevantDelays = delays.filter(item => key(item.service) === key(service) || key(item.service) === 'todas');
  const generalDelay = relevantDelays.some(item => key(item.zone) === key(ALL_DEPARTMENT));
  const zones = new Map();
  if (!generalDelay) {
    for (const item of relevant) {
      if (key(item.zone) === key(ALL_DEPARTMENT)) continue;
      for (const zone of members(item)) zones.set(key(zone), zone);
    }
  }
  for (const item of relevantDelays) {
    if (key(item.zone) === key(ALL_DEPARTMENT)) continue;
    for (const zone of members(item)) zones.set(key(zone), zone);
  }
  const groups = new Map();
  for (const zone of zones.values()) {
    const standard = arrivalReference(relevant, service, zone);
    const situation = arrivalSituation({delays, items: relevant, service, zone, mapStatus, standardStatus, standard, requireZone: false});
    const signature = [standard?.id || '', situation.state, ...situation.matching.map(item => item.id).sort((a,b) => a-b)].join(':');
    if (!groups.has(signature)) groups.set(signature, { zones: [], standard, situation, scope: 'zone' });
    groups.get(signature).zones.push(zone);
  }
  const rows = [...groups.values()].map(group => ({...group, label: group.zones.join(', ')}));
  const standard = arrivalReference(relevant, service, ALL_DEPARTMENT);
  const situation = arrivalSituation({delays, items: relevant, service, zone: ALL_DEPARTMENT,
    mapStatus, standardStatus, standard, requireZone: false});
  rows.push({scope: 'department', zones: [], label: rows.length ? 'Resto del departamento' : 'Todo el departamento', standard, situation});
  return rows;
}
