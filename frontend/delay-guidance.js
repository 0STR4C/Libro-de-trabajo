const ALL_DEPARTMENT = 'todo el departamento';
const key = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLocaleLowerCase();

export function matchingExceptions(delays, service, zone) {
  if (!service || !zone) return [];
  return (delays || []).filter(item => {
    const itemService = key(item.service);
    const itemZone = key(item.zone);
    return (itemService === key(service) || itemService === 'todas')
      && (itemZone === ALL_DEPARTMENT || itemZone.split(',').some(part => part.trim() === key(zone)));
  });
}

export function delayGuidance(item) {
  if (item.needs_review) {
    if (item.message === 'Margen de') return 'Margen informado anteriormente. Verificar antes de comunicar un tiempo.';
    if (item.message === 'Máximo de') return 'Máximo informado anteriormente. Verificar antes de comunicar un tiempo.';
    if (item.message === 'Intervalo estimado') return 'Intervalo informado anteriormente. Verificar antes de comunicar un tiempo.';
    if (item.message === 'Otra indicación') return `${item.instruction_text || 'Indicación operativa'}. Verificar vigencia antes de comunicar.`;
    if (item.message === 'A confirmar') return 'Tiempo pendiente de confirmación. Verificar el estado actual.';
    return `${item.message || 'Demora registrada'}. Verificar antes de comunicar.`;
  }
  if (item.message === 'Máximo de' && item.minutes) return `Máximo informado: ${item.minutes} min.`;
  if (item.message === 'Intervalo estimado' && item.minutes_min && item.minutes_max)
    return `Entre ${item.minutes_min} y ${item.minutes_max} min estimados.`;
  if (item.message === 'Otra indicación') return item.instruction_text || 'Indicación operativa pendiente de detalle';
  return item.message === 'Margen de' && item.minutes
    ? `Margen informado: ${item.minutes} min. No equivale al tiempo total de llegada.`
    : item.message || 'Tiempo por confirmar';
}
