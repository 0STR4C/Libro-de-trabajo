const lower = value => String(value ?? '').toLocaleLowerCase('es-UY');
const connectors = new Set(['a', 'de', 'del', 'el', 'en', 'la', 'las', 'los', 'o', 'y']);

export function displayLocation(value) {
  let first = true;
  return lower(value).split(/([\s,/-]+)/u).map(part => {
    if (!part || /^[\s,/-]+$/u.test(part)) return part;
    const result = !first && connectors.has(part) ? part : part.replace(/^\p{L}/u, letter => letter.toLocaleUpperCase('es-UY'));
    first = false;
    return result;
  }).join('');
}

export function displayService(value) {
  if (lower(value).trim() === 'ml') return 'Mecánica Ligera';
  return displayLocation(value);
}
