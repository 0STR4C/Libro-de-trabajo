import test from 'node:test';
import assert from 'node:assert/strict';
import { routes, parseRoute, routeUrl, allowedRoute, firstAllowedRoute } from '../frontend/routes.js';

test('every direct route has one stable path and a permission', () => {
  assert.equal(new Set(routes.map(route => route.path)).size, routes.length);
  for (const route of routes) {
    assert.ok(route.permission);
    assert.equal(parseRoute(route.path).route, route);
  }
});

test('query parameters survive only when valid and non-sensitive', () => {
  const route=parseRoute('/horarios','?week=2026-09-07&view=mine&phone=099000111');
  assert.deepEqual(route.filters,{week:'2026-09-07',view:'mine'});
  assert.equal(routeUrl(route.route,route.filters),'/horarios?week=2026-09-07&view=mine');
  assert.deepEqual(parseRoute('/horarios','?week=2026-02-30&view=unknown').filters,{});
  assert.deepEqual(parseRoute('/avisos','?status=EN_GESTION&contact=099000111').filters,{status:'EN_GESTION'});
  const history=parseRoute('/cotizador','?tab=history');
  assert.equal(routeUrl(history.route,history.filters),'/cotizador?tab=history');
  assert.equal(parseRoute('/missing').route,null);
});

test('authorization uses the route, not just the visible menu', () => {
  const actor={role_name:'Telefonista',permissions:['dashboard.view','schedules.view']};
  assert.equal(firstAllowedRoute(actor).path,'/resumen');
  assert.equal(allowedRoute(parseRoute('/horarios').route,actor),true);
  assert.equal(allowedRoute(parseRoute('/supervision/planificacion').route,actor),false);
  assert.equal(allowedRoute(parseRoute('/configuracion').route,actor),false);
  assert.equal(allowedRoute(parseRoute('/configuracion/tiempos-estandar').route,{...actor,permissions:['settings.manage','standards.view']}),true);
  assert.equal(allowedRoute(parseRoute('/configuracion/tiempos-estandar').route,{...actor,permissions:['settings.manage']}),false);
});
