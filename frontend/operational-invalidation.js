// Solo invalida vistas que consumen datos de la entidad modificada.
export function affectedViews(url) {
  const path = new URL(url, 'http://local.invalid').pathname;
  if (/^\/api\/delays(?:\/|$)/.test(path)) return ['dashboard', 'delayAudit', 'supervision'];
  if (/^\/api\/(?:notices|transfers)(?:\/|$)/.test(path)) return ['supervision'];
  if (/^\/api\/arrival-times(?:\/|$)/.test(path)) return ['dashboard', 'supervision'];
  if (/^\/api\/(?:wfm|schedules)(?:\/|$)/.test(path)) return ['schedules', 'supervision'];
  return [];
}
