// One catalogue for navigation, titles, links and frontend authorization.
export const routes = [
  { page: 'dashboard', path: '/resumen', title: 'Resumen operativo', label: 'Resumen', icon: 'pi-home', permission: 'dashboard.view', group: 'operation' },
  { page: 'notices', path: '/avisos', title: 'Avisos del equipo', label: 'Avisos', icon: 'pi-bell', permission: 'notices.view', group: 'operation' },
  { page: 'quotes', path: '/cotizador', title: 'Cotizador de servicios', label: 'Cotizador', icon: 'pi-calculator', permission: 'quotes.view', group: 'operation' },
  { page: 'delays', path: '/demoras', title: 'Zonas con demora', label: 'Zonas con demora', icon: 'pi-map-marker', permission: 'delays.view', group: 'operation' },
  { page: 'transfers', path: '/programados', title: 'Programados', label: 'Programados', icon: 'pi-send', permission: 'transfers.view', group: 'operation' },
  { page: 'schedules', path: '/horarios', title: 'Horarios', label: 'Horarios', icon: 'pi-calendar', permission: 'schedules.view', group: 'operation' },
  { page: 'requests', path: '/solicitudes', title: 'Mis solicitudes', label: 'Mis solicitudes', icon: 'pi-inbox', permission: 'schedules.view', roles: ['Telefonista', 'Planificador', 'Supervisor'], group: 'operation' },
  { page: 'supervision', path: '/supervision/dashboard', title: 'Dashboard de Supervisión', label: 'Dashboard', icon: 'pi-chart-bar', permission: 'dashboard.view', roles: ['Supervisor', 'Administrador'], group: 'supervision' },
  { page: 'delayAudit', path: '/supervision/auditoria-demoras', title: 'Auditoría de demoras', label: 'Auditoría de demoras', icon: 'pi-history', permission: 'delays.view', roles: ['Supervisor', 'Administrador'], group: 'supervision' },
  { page: 'wfm', path: '/supervision/planificacion', title: 'Planificación de horarios', label: 'Planificación de horarios', icon: 'pi-users', permission: 'schedules.view', roles: ['Supervisor', 'Administrador'], group: 'supervision' },
  { page: 'audit', path: '/supervision/auditoria', title: 'Registro de auditoría', label: 'Auditoría general', icon: 'pi-list', permission: 'audit.view', group: 'supervision' },
  { page: 'settings', path: '/configuracion', title: 'Configuración', label: 'Configuración', icon: 'pi-cog', permission: 'settings.manage', group: 'settings', tab: 'roles' },
  { page: 'settings', path: '/configuracion/general', title: 'Configuración', label: 'Configuración', icon: 'pi-cog', permission: 'settings.manage', tab: 'general' },
  { page: 'settings', path: '/configuracion/tiempos-estandar', title: 'Tiempos estándar de llegada', label: 'Tiempos estándar de llegada', icon: 'pi-clock', permission: 'arrival_times.manage', tab: 'arrival-times' },
  { page: 'settings', path: '/configuracion/novedades', title: 'Configuración', label: 'Novedades', icon: 'pi-info-circle', permission: 'settings.manage', tab: 'news' },
  { page: 'settings', path: '/configuracion/usuarios', title: 'Configuración', label: 'Usuarios', icon: 'pi-users', permission: 'settings.manage', tab: 'users' },
  { page: 'settings', path: '/configuracion/roles', title: 'Configuración', label: 'Roles y permisos', icon: 'pi-lock', permission: 'settings.manage', tab: 'roles' },
  { page: 'settings', path: '/configuracion/acceso-google', title: 'Configuración', label: 'Acceso Google', icon: 'pi-google', permission: 'settings.manage', tab: 'google' },
  { page: 'settings', path: '/configuracion/tarifas', title: 'Configuración', label: 'Tarifas cotizador', icon: 'pi-dollar', permission: 'settings.manage', tab: 'quotes' },
  { page: 'settings', path: '/configuracion/catalogos', title: 'Configuración', label: 'Catálogos', icon: 'pi-list', permission: 'settings.manage', tab: 'catalogs' },
];

export const routeFor = (page, tab = 'roles') => routes.find(route => route.page === page && (page !== 'settings' || route.tab === tab)) || routes.find(route => route.page === page);
export const allowedRoute = (route, actor) => {
  if(!route || !actor)return false;
  const permissions=actor.permissions||[];
  if(route.tab==='arrival-times')return permissions.includes('standards.view') && (permissions.includes('settings.manage')||permissions.includes('arrival_times.manage'));
  return permissions.includes(route.permission) && (!route.roles || route.roles.includes(actor.role_name));
};
export const firstAllowedRoute = actor => routes.find(route => route.group === 'operation' && allowedRoute(route, actor)) || routes.find(route => allowedRoute(route, actor));

const day = value => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return '';
  const parsed = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value ? '' : value;
};
const choices = values => value => values.includes(value) ? value : '';
const limited = (pattern, max = 80) => value => value && value.length <= max && pattern.test(value) ? value : '';
const date = day;
const pageParams = {
  quotes: { tab: choices(['new','history']) },
  notices: { view: choices(['open','unassigned','mine','waiting','resolved','all']), status: choices(['PENDIENTE','EN_GESTION','ESPERANDO_RESPUESTA','RESUELTO','CANCELADO']), from: date, to: date },
  delays: { view: choices(['active','review','history','all']), from: date, to: date, department: limited(/^[\p{L} .'-]+$/u), service: choices(['GRÚA','ML','SINIESTROS','TODAS']) },
  delayAudit: { scope: choices(['all','current','review','normalized']), from: date, to: date, department: limited(/^[\p{L} .'-]+$/u) },
  transfers: { view: choices(['active','finished','cancelled','all']), status: choices(['SIN_ASIGNAR','ASIGNADO','EN_CURSO','FINALIZADO','CANCELADO']), from: date, to: date },
  schedules: { week: value => { const valid=day(value); return valid && new Date(`${valid}T12:00:00Z`).getUTCDay() === 1 ? valid : ''; }, view: choices(['team','mine']) },
  wfm: { day: date, team: choices(['Telefonista','Planificador','Supervisor']) },
  audit: { from: date, to: date, entity: limited(/^[a-z_]+$/i, 40), action: limited(/^[A-Z_]+$/, 50) },
  settings: { department: limited(/^[\p{L} .'-]+$/u), service: choices(['GRÚA','ML','SINIESTROS']), status: choices(['all','active','inactive']) },
};

export function parseRoute(pathname, search = '') {
  if (pathname === '/') return { route: routeFor('dashboard'), root: true, filters: {} };
  const route = routes.find(item => item.path === pathname.replace(/\/$/, ''));
  if (!route) return { route: null, root: false, filters: {} };
  const query = new URLSearchParams(search);
  const validators = pageParams[route.page] || {};
  const filters = {};
  for (const [key, validate] of Object.entries(validators)) {
    if (route.page === 'settings' && route.tab !== 'arrival-times') break;
    const value = validate(query.get(key) || '');
    if (value) filters[key] = value;
  }
  return { route, root: false, filters };
}

export function routeUrl(route, filters = {}) {
  if (!route) return '/resumen';
  const params = new URLSearchParams();
  if (route.page === 'settings' && route.tab !== 'arrival-times') return route.path;
  for (const [key, validate] of Object.entries(pageParams[route.page] || {})) {
    const value = validate(String(filters[key] ?? ''));
    if (value) params.set(key, value);
  }
  return route.path + (params.size ? `?${params}` : '');
}
