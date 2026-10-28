const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const projectRoot = path.resolve(process.env.PROJECT_ROOT || path.join(__dirname, '../..'));
const staticRoot = path.join(projectRoot, 'app/static');
const bundleRoot = path.resolve(process.env.BUNDLE_ROOT || path.join(staticRoot, 'frontend'));
const longDetail = 'Coordinación pendiente para ' + 'Zona operativa extensa '.repeat(24);
const actor = {id: 501, display_name: 'Operador Sintético', role_name: 'Supervisor', permissions: [
  'dashboard.view', 'notices.view', 'notices.create', 'notices.assign', 'notices.comment',
  'notices.change_status', 'notices.close', 'delays.view', 'standards.view'
]};
const firstNotice = () => ({id: 11, revision: 1, task_number: 'QA-101', phone: '099000111',
  notice_type: 'Volverán a llamar', audience: 'TODOS', detail: longDetail,
  communicated_by: 'Telefonista Sintético', managed_by: null, status: 'PENDIENTE',
  comments: null, created_at: '2026-10-14T10:00:00-03:00'});
const secondNotice = () => ({id: 12, revision: 1, task_number: 'QA-202', phone: '099000222',
  notice_type: 'Reclama no cumplimiento', audience: 'TODOS', detail: 'Solicita seguimiento',
  communicated_by: 'Telefonista Sintético', managed_by: actor.display_name, status: 'EN_GESTION',
  comments: null, created_at: '2026-10-14T09:00:00-03:00'});

function staticServer() {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://localhost');
    let file;
    if (url.pathname === '/' || (!url.pathname.startsWith('/api/') && !url.pathname.startsWith('/static/') && !path.basename(url.pathname).includes('.'))) file = path.join(staticRoot, 'index.html');
    else if (url.pathname.startsWith('/static/frontend/')) file = path.join(bundleRoot, url.pathname.slice('/static/frontend/'.length));
    else if (url.pathname.startsWith('/static/')) file = path.join(staticRoot, url.pathname.slice('/static/'.length));
    else file = path.join(staticRoot, url.pathname.slice(1));
    const allowed = [staticRoot, bundleRoot].some(root => file.startsWith(root + path.sep));
    if (!allowed || !fs.existsSync(file) || !fs.statSync(file).isFile()) { response.writeHead(404); response.end('Not found'); return; }
    const type = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.geojson':'application/geo+json', '.svg':'image/svg+xml', '.woff2':'font/woff2'}[path.extname(file)] || 'application/octet-stream';
    response.writeHead(200, {'Content-Type':`${type}; charset=utf-8`, 'Cache-Control':'no-store'});
    fs.createReadStream(file).pipe(response);
  });
}

function syntheticApi() {
  const state = {signedIn:false, actor, notices:[firstNotice(), secondNotice()], requests:[],
    arrivalItems:[
      {id:1,service:'ML',department:'MONTEVIDEO',zone:'Todo el departamento',base_estimated_minutes:60,revision:1},
      {id:2,service:'ML',department:'MONTEVIDEO',zone:'Pocitos',base_estimated_minutes:40,revision:1},
      {id:4,service:'GRÚA',department:'MONTEVIDEO',zone:'Todo el departamento',base_estimated_minutes:75,revision:1},
    ],
    nextId:13, unexpected:[], onRequest:null, postCount:0, patchCount:0};
  const respond = (route, status, body) => route.fulfill({status, contentType:'application/json', body:JSON.stringify(body)});
  const handler = async route => {
    const request = route.request(), url = new URL(request.url()), pathname = url.pathname;
    const entry = {method:request.method(), pathname, query:Object.fromEntries(url.searchParams), body:request.postDataJSON?.()};
    state.requests.push(entry);
    if (state.onRequest && await state.onRequest(entry, route, respond)) return;
    if (pathname === '/api/auth/me') return respond(route, state.signedIn ? 200 : 401, state.signedIn ? state.actor : {detail:'Sesión requerida'});
    if (pathname === '/api/auth/login') { state.signedIn = true; return respond(route, 200, {ok:true}); }
    if (pathname === '/api/auth/logout') { state.signedIn = false; return respond(route, 200, {ok:true}); }
    if (!state.signedIn) return respond(route, 401, {detail:'Sesión requerida'});
    if (pathname === '/api/dashboard/map-stats') return respond(route, 200, {departments:[{department:'MONTEVIDEO',delays:[]},{department:'CANELONES',delays:[]}], updated_at:'2026-10-14T10:00:00-03:00'});
    if (pathname === '/api/arrival-times/overview') return respond(route, 200, {departments:{MONTEVIDEO:state.arrivalItems,CANELONES:[]}});
    if (pathname === '/api/arrival-times/geography') return respond(route, 200, {services:['ML','GRÚA','SINIESTROS'],departments:{MONTEVIDEO:['Todo el departamento','Pocitos','Buceo']}});
    if (pathname === '/api/arrival-times/department') return respond(route, 200, {department:'MONTEVIDEO',items:state.arrivalItems});
    if (pathname === '/api/arrival-times/resolve') {
      const scope = entry.query.zone === 'Pocitos' ? 'zone' : 'department';
      return respond(route, 200, {status:'configured',service:entry.query.service,department:'MONTEVIDEO',requested_zone:entry.query.zone,
        base_estimated_minutes:scope==='zone'?40:60,unit:'minutes',scope,source_zone:scope==='zone'?'Pocitos':'Todo el departamento',arrival_time_id:scope==='zone'?2:1,revision:1,updated_at:'2026-10-14T10:00:00-03:00'});
    }
    if (pathname === '/api/arrival-times' && entry.method === 'GET') return respond(route, 200, {items:[
      {id:1,service:'ML',department:'MONTEVIDEO',zone:'Todo el departamento',base_estimated_minutes:60,is_active:true,revision:1},
      {id:2,service:'ML',department:'MONTEVIDEO',zone:'Pocitos',base_estimated_minutes:40,is_active:true,revision:1},
      {id:3,service:'GRÚA',department:'MONTEVIDEO',zone:'Buceo',base_estimated_minutes:75,is_active:true,revision:1,seed_key:'arrival-time-seed-v1-03'},
    ],total:3,limit:50,offset:0});
    if (pathname === '/api/arrival-times/2' && entry.method === 'PATCH') return respond(route, 409, {detail:'El tiempo de arribo cambió'});
    if (pathname === '/api/arrival-times/2' && entry.method === 'GET') return respond(route, 200, {id:2,service:'ML',department:'MONTEVIDEO',zone:'Pocitos',base_estimated_minutes:50,is_active:true,revision:2});
    if (pathname === '/api/operational-alerts') return respond(route, 200, []);
    if (pathname === '/api/quotes/history') return respond(route, 200, []);
    if (pathname === '/api/delays/geography') return respond(route, 200, {MONTEVIDEO:['Todo el departamento','Pocitos']});
    if (pathname === '/api/delays' && entry.method === 'GET') return respond(route, 200, {items:[],total:0,limit:50,offset:0});
    if (pathname === '/api/delays/page') return respond(route, 200, {items:[],total:0,limit:50,offset:0});
    if (pathname === '/api/transfers' && entry.method === 'GET') return respond(route, 200, []);
    if (pathname === '/api/schedules/team') return respond(route, 200, {people:[{id:501,display_name:'Operador Sintético',role_name:'Supervisor'}],rows:[]});
    if (pathname === '/api/audit/page') return respond(route, 200, {items:[],total:0,limit:50,offset:0});
    if (pathname === '/api/wfm/plan') return respond(route, 200, {revision:1,published_revision:0,window:[0,48],people:[],shifts:[],demand:Array(48).fill(0),requirements:[],weekly_schedule:[],settings:{}});
    if (pathname === '/api/wfm/requests') return respond(route, 200, []);
    if (pathname === '/api/dashboard') return respond(route, 200, {as_of:'2026-10-14T10:00:00-03:00',period_days:30,notices_open:2,transfers_pending:0,delays_current:0,delays_need_review:0,distributions:{}});
    if (pathname === '/api/settings/roles') return respond(route, 200, [{id:1,name:'Supervisor',permissions:[],revision:1}]);
    if (pathname === '/api/settings/permissions') return respond(route, 200, []);
    if (pathname === '/api/settings/version') return respond(route, 200, {version:'1.32.0',releases:[]});
    if (pathname === '/api/notices/page') {
      const q = (url.searchParams.get('q') || '').toLowerCase();
      const task = (url.searchParams.get('task') || '').toLowerCase();
      const contact = (url.searchParams.get('contact') || '').toLowerCase();
      const status = url.searchParams.get('status') || '';
      const scope = url.searchParams.get('scope') || 'open';
      let rows = state.notices.filter(item => (!q || [item.task_number,item.detail,item.notice_type].join(' ').toLowerCase().includes(q)) &&
        (!task || item.task_number?.toLowerCase().includes(task)) && (!contact || item.phone?.includes(contact)) &&
        (!status || item.status === status) && (scope !== 'open' || !['RESUELTO','CANCELADO'].includes(item.status)));
      if (scope === 'unassigned') rows = rows.filter(item => !item.managed_by);
      if (scope === 'mine') rows = rows.filter(item => item.managed_by === actor.display_name);
      if (scope === 'waiting') rows = rows.filter(item => item.status === 'ESPERANDO_RESPUESTA');
      if (scope === 'resolved') rows = rows.filter(item => ['RESUELTO','CANCELADO'].includes(item.status));
      const offset = Number(url.searchParams.get('offset') || 0), limit = Number(url.searchParams.get('limit') || 50);
      return respond(route, 200, {items:rows.slice(offset,offset+limit), total:rows.length, offset, limit,
        counts:{open:state.notices.filter(item => !['RESUELTO','CANCELADO'].includes(item.status)).length,
          unassigned:state.notices.filter(item => !item.managed_by).length,
          mine:state.notices.filter(item => item.managed_by === actor.display_name).length,
          waiting:state.notices.filter(item => item.status === 'ESPERANDO_RESPUESTA').length}});
    }
    if (pathname === '/api/notices/duplicates') return respond(route, 200, []);
    if (pathname === '/api/notices/assignees') return respond(route, 200, [{display_name:actor.display_name,role_name:'Supervisor'}]);
    if (/^\/api\/notices\/\d+\/history$/.test(pathname)) return respond(route, 200, []);
    if (/^\/api\/notices\/\d+$/.test(pathname)) return respond(route, 200, state.notices.find(item => item.id === Number(pathname.split('/').at(-1))) || {});
    if (pathname === '/api/notices' && entry.method === 'POST') {
      state.postCount += 1;
      const row = {...entry.body,id:state.nextId++,revision:1,created_at:'2026-10-14T11:00:00-03:00'};
      state.notices.unshift(row);
      return respond(route, 201, row);
    }
    if (/^\/api\/notices\/\d+\/status$/.test(pathname) && entry.method === 'PATCH') {
      state.patchCount += 1;
      const item = state.notices.find(row => row.id === Number(pathname.split('/')[3]));
      Object.assign(item, entry.body, {revision:item.revision+1});
      return respond(route, 200, item);
    }
    state.unexpected.push(`${entry.method} ${pathname}`);
    return respond(route, 501, {detail:'Petición sintética no prevista'});
  };
  return {state, handler};
}

let server, browser, baseUrl;
before(async () => {
  server = staticServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({headless:true, ...(process.env.BROWSER_CHANNEL ? {channel:process.env.BROWSER_CHANNEL} : {})});
});
after(async () => { await browser?.close(); await new Promise(resolve => server?.close(resolve)); });

async function fixture(t) {
  const context = await browser.newContext({viewport:{width:1366,height:768}});
  const page = await context.newPage(), api = syntheticApi(), pageErrors=[];
  page.setDefaultTimeout(6000);
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.route('**/api/**', api.handler);
  await page.route('**/uruguay-departamentos.geojson', route => respondGeo(route));
  await page.goto(baseUrl, {waitUntil:'domcontentloaded'});
  t.after(async () => { assert.deepEqual(api.state.unexpected, [], 'No debe haber peticiones API sin fixture'); assert.deepEqual(pageErrors, [], 'React no debe lanzar errores'); await context.close(); });
  return {page, api:api.state};
}
function respondGeo(route) { return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({type:'FeatureCollection',features:[
  {type:'Feature',properties:{nam:'MONTEVIDEO'},geometry:{type:'Polygon',coordinates:[[[-57,-35],[-56,-35],[-56,-34],[-57,-34],[-57,-35]]]}},
  {type:'Feature',properties:{nam:'CANELONES'},geometry:{type:'Polygon',coordinates:[[[-57,-34],[-56,-34],[-56,-33],[-57,-33],[-57,-34]]]}}
]})}); }
async function signIn(page, destination = 'Resumen operativo') {
  await page.getByRole('textbox',{name:'Usuario o correo electrónico'}).fill('operador.sintetico');
  await page.getByLabel('Contraseña',{exact:true}).fill('clave-de-prueba');
  await page.getByRole('button',{name:'Ingresar'}).click();
  await page.getByRole('heading',{name:destination}).waitFor();
}
async function notices(page) {
  await page.locator('[data-page="notices"]').click();
  await page.getByRole('heading',{name:'Avisos del equipo'}).waitFor();
  await page.locator('.notice-prime-table.p-datatable').waitFor();
}
function deferred() { let resolve; const promise = new Promise(done => {resolve=done;}); return {promise,resolve}; }
async function until(check, message) {
  for (let attempt=0; attempt<100; attempt++) { if (check()) return; await new Promise(resolve=>setTimeout(resolve,20)); }
  throw new Error(message);
}

test('Rutas React: ingreso directo, historial, filtros recuperables y permisos', async t => {
  const {page,api} = await fixture(t);
  api.actor={...actor,permissions:[...actor.permissions,'quotes.view','transfers.view','schedules.view','settings.manage']};
  await page.goto(`${baseUrl}/avisos`,{waitUntil:'domcontentloaded'});
  await page.getByRole('textbox',{name:'Usuario o correo electrónico'}).fill('operador.sintetico');
  await page.getByLabel('Contraseña',{exact:true}).fill('clave-de-prueba');
  await page.getByRole('button',{name:'Ingresar'}).click();
  await page.getByRole('heading',{name:'Avisos del equipo'}).waitFor();
  assert.equal(new URL(page.url()).pathname,'/avisos');
  await page.reload();
  await page.getByRole('heading',{name:'Avisos del equipo'}).waitFor();
  await page.locator('[data-page="transfers"]').click();
  await page.getByRole('heading',{name:'Programados'}).waitFor();
  assert.equal(new URL(page.url()).pathname,'/programados');
  await page.goBack();
  await page.getByRole('heading',{name:'Avisos del equipo'}).waitFor();
  await page.goForward();
  await page.getByRole('heading',{name:'Programados'}).waitFor();
  const link=page.locator('[data-page="schedules"]');
  assert.equal(new URL(await link.getAttribute('href'),baseUrl).pathname,'/horarios');
  await page.goto(`${baseUrl}/horarios?week=2026-09-07&view=mine&phone=099000111`);
  await page.getByRole('heading',{name:'Horarios'}).waitFor();
  assert.equal(new URL(page.url()).searchParams.get('week'),'2026-09-07');
  assert.equal(new URL(page.url()).searchParams.get('phone'),null);
  await page.reload();
  await page.getByRole('heading',{name:'Horarios'}).waitFor();
  assert.equal(new URL(page.url()).searchParams.get('week'),'2026-09-07');
  const newTab=page.context().waitForEvent('page');
  await page.locator('[data-page="transfers"]').click({button:'middle'});
  const newPage=await newTab;
  await newPage.waitForLoadState('domcontentloaded');
  assert.equal(new URL(newPage.url()).pathname,'/programados');
  await newPage.close();
  await page.goto(`${baseUrl}/cotizador?tab=history`);
  await page.getByText('Historial · 0 cotizaciones').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('tab'),'history');
  await page.goto(`${baseUrl}/supervision/planificacion?day=2026-10-14&team=Planificador`);
  await page.getByRole('heading',{name:'Planificación de horarios'}).waitFor();
  assert.equal(new URL(page.url()).searchParams.get('team'),'Planificador');
  await page.goto(`${baseUrl}/configuracion/roles`);
  await page.getByRole('heading',{name:'Configuración'}).waitFor();
  await page.goto(`${baseUrl}/supervision/auditoria`);
  await page.getByText('Acceso no permitido').waitFor();
  await page.goto(`${baseUrl}/seccion-inexistente`);
  await page.getByRole('heading',{name:'Página no encontrada'}).waitFor();
  assert.equal(api.unexpected.length,0,`API inesperada: ${api.unexpected.join(', ')}`);
});

test('React real: login, navegación, filtro Enter, respuestas fuera de orden, vacío y textos largos', async t => {
  const {page,api} = await fixture(t);
  await page.getByRole('textbox',{name:'Usuario o correo electrónico'}).waitFor();
  assert.equal(await page.getByRole('textbox',{name:'Usuario o correo electrónico'}).count(),1);
  assert.equal(await page.getByLabel('Contraseña',{exact:true}).count(),1);
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('autocomplete')),'username');
  await signIn(page);
  const initial=deferred();
  api.onRequest=async (entry,route,respond)=>{
    if(entry.pathname==='/api/notices/page') { await initial.promise; await respond(route,200,{items:[firstNotice(),secondNotice()],total:2,offset:0,limit:50,counts:{open:2,unassigned:1,mine:1,waiting:0}}); return true; }
    return false;
  };
  await page.locator('[data-page="notices"]').click();
  await until(()=>api.requests.some(item=>item.pathname==='/api/notices/page'),'No llegó la carga inicial de Avisos');
  const loading=page.locator('#content [role="status"]:visible').filter({hasText:'Cargando información'});
  await loading.waitFor();
  initial.resolve();
  await page.locator('.notice-prime-table.p-datatable').waitFor();
  api.onRequest=null;
  assert.equal(await page.locator('.notice-prime-table tbody tr').count(),2);
  assert.equal(await page.locator('.notice-prime-table').count(),1);
  assert.equal(await page.locator('.notice-prime-table').getAttribute('class').then(value=>value.includes('p-datatable')),true);
  const search=page.getByRole('textbox',{name:'Búsqueda'});
  await search.fill('QA-101'); await search.press('Enter');
  await page.getByText('1 avisos').waitFor();
  assert.equal(api.requests.at(-1).query.q,'QA-101');
  const first=deferred(), second=deferred(), firstSettled=deferred();
  api.onRequest = async (entry,route,respond) => {
    if(entry.pathname==='/api/notices/page' && ['primera','segunda'].includes(entry.query.q)) {
      const gate=entry.query.q==='primera'?first:second;
      await gate.promise;
      await respond(route,200,{items:entry.query.q==='segunda'?[secondNotice()]:[firstNotice()],total:1,offset:0,limit:50,counts:{open:2,unassigned:1,mine:1,waiting:0}});
      if(entry.query.q==='primera')firstSettled.resolve();
      return true;
    }
    return false;
  };
  await search.fill('primera'); await search.press('Enter');
  await until(()=>api.requests.some(item=>item.query.q==='primera'),'No llegó el primer filtro');
  await search.fill('segunda'); await search.press('Enter');
  await until(()=>api.requests.some(item=>item.query.q==='segunda'),'No llegó el segundo filtro');
  second.resolve();
  await page.getByText('QA-202').waitFor();
  first.resolve();
  await firstSettled.promise;
  assert.equal(await page.getByText('QA-202').count(),1,'La respuesta vieja no debe reemplazar el resultado nuevo');
  api.onRequest=null;
  await search.fill('sin-resultados'); await search.press('Enter');
  await page.getByText('No hay avisos para esos filtros').waitFor();
  await page.getByRole('button',{name:'Limpiar'}).click();
  await page.getByText('QA-101').waitFor();
  await page.locator('.notice-prime-table tbody tr').filter({hasText:'QA-101'}).click();
  const dialog=page.getByRole('dialog',{name:'Aviso completo'});
  await dialog.getByText(longDetail).waitFor();
  assert.equal(await dialog.getByText(longDetail).count(),1);
  await page.keyboard.press('Escape');
  await dialog.waitFor({state:'hidden'});
});

test('React real: menú de fila por teclado, validación, doble envío, guardado y conflicto', async t => {
  const {page,api}=await fixture(t); await signIn(page); await notices(page);
  const row=page.locator('.notice-prime-table tbody tr').filter({hasText:'QA-101'});
  const menuButton=row.getByRole('button',{name:'Acciones del aviso QA-101'});
  await menuButton.focus(); await page.keyboard.press('Enter');
  await page.getByRole('menuitem',{name:'Historial'}).waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('menuitem',{name:'Historial'}).waitFor({state:'hidden'});
  const create=page.getByRole('button',{name:'Nuevo aviso'});
  await create.click();
  const dialog=page.getByRole('dialog',{name:'Registrar nuevo aviso'});
  await dialog.waitFor();
  assert.equal(await dialog.evaluate(node=>node.contains(document.activeElement)),true,'El foco inicial debe quedar dentro del diálogo');
  assert.equal(await dialog.getByRole('textbox',{name:'Número de tarea'}).count(),1);
  assert.equal(await dialog.getByRole('textbox',{name:'Teléfono del cliente'}).count(),1);
  await page.keyboard.press('Escape'); await dialog.waitFor({state:'hidden'});
  await page.waitForFunction(() => document.activeElement?.textContent?.includes('Nuevo aviso'));
  assert.equal(await create.evaluate(node=>node===document.activeElement),true,'El foco debe volver a Nuevo aviso');
  await create.click(); await dialog.waitFor();
  await dialog.getByRole('button',{name:'Guardar'}).click();
  assert.equal(api.postCount,0,'Un formulario inválido no debe enviar POST');
  const motive = dialog.getByRole('textbox',{name:'Motivo'});
  assert.equal(await motive.count(),1,'El selector debe exponer un campo con nombre accesible');
  assert.equal(await motive.evaluate(node=>node.id && document.querySelector(`label[for="${CSS.escape(node.id)}"]`)?.textContent?.includes('Motivo')),true,'La etiqueta debe apuntar al campo del selector');
  await dialog.locator('.p-dropdown').first().click();
  await page.getByRole('option',{name:'Volverán a llamar'}).click();
  await dialog.getByRole('textbox',{name:'¿Qué necesita saber o hacer el equipo?'}).fill('Aviso sintético para doble envío.');
  api.onRequest=async (entry,route,respond)=>{
    if(entry.pathname==='/api/notices'&&entry.method==='POST') {api.postCount+=1; await respond(route,422,{detail:'Detalle inválido de prueba'}); return true;}
    return false;
  };
  await dialog.getByRole('button',{name:'Guardar'}).click();
  await page.getByRole('alert').filter({hasText:'Detalle inválido de prueba'}).waitFor();
  assert.equal(await dialog.getByRole('button',{name:'Guardar'}).isEnabled(),true,'Tras el error debe poder reintentarse');
  const gate=deferred();
  api.onRequest=async (entry,route,respond)=>{
    if(entry.pathname==='/api/notices'&&entry.method==='POST') {
      api.postCount+=1; await gate.promise;
      const item={...entry.body,id:api.nextId++,revision:1,created_at:'2026-10-14T11:00:00-03:00'};
      api.notices.unshift(item); await respond(route,201,item); return true;
    }
    return false;
  };
  await dialog.getByRole('button',{name:'Guardar'}).click();
  await page.waitForFunction(() => document.querySelector('.p-dialog button[type="submit"]')?.disabled === true);
  await dialog.locator('form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  assert.equal(api.postCount,2,'El doble envío no debe repetir el POST pendiente');
  gate.resolve(); await dialog.waitFor({state:'hidden'});
  await page.getByText('Aviso sintético para doble envío.').first().waitFor();
  api.onRequest=null;
  await menuButton.focus(); await page.keyboard.press('Enter');
  await page.getByRole('menuitem',{name:'Editar seguimiento'}).click();
  const edit=page.getByRole('dialog',{name:'Editar seguimiento'});
  await edit.getByRole('textbox',{name:'Comentario de seguimiento'}).fill('Borrador conservado');
  api.onRequest=async (entry,route,respond)=>{
    if(entry.pathname==='/api/notices/11/status'&&entry.method==='PATCH') {api.patchCount+=1; await respond(route,409,{detail:'Conflicto de revisión'}); return true;}
    return false;
  };
  await edit.getByRole('button',{name:'Guardar'}).click();
  await edit.getByRole('alert').getByText('El aviso cambió mientras lo editabas.').waitFor();
  assert.equal(await edit.getByRole('textbox',{name:'Comentario de seguimiento'}).inputValue(),'Borrador conservado');
  assert.equal(await edit.getByRole('button',{name:'Guardar'}).isDisabled(),true);
  await edit.getByRole('button',{name:'Descartar borrador'}).click();
  await edit.waitFor({state:'hidden'});
});

test('React real: confirmación, Escape, logout pendiente y cambio de sesión', async t => {
  const {page,api}=await fixture(t); await signIn(page); await notices(page);
  const exit=page.getByRole('button',{name:'Salir'}).first();
  await exit.click();
  const dialog=page.getByRole('dialog',{name:'Cerrar sesión'}); await dialog.waitFor();
  assert.equal(await dialog.evaluate(node=>node.contains(document.activeElement)),true,'El foco inicial de confirmación debe quedar en el diálogo');
  await page.keyboard.press('Escape'); await dialog.waitFor({state:'hidden'});
  await page.waitForFunction(() => document.activeElement?.textContent?.trim()==='Salir');
  assert.equal(await exit.evaluate(node=>node===document.activeElement),true,'Escape debe devolver el foco a Salir');
  assert.equal(api.signedIn,true);
  await exit.click(); await dialog.getByRole('button',{name:'Cancelar'}).click();
  assert.equal(api.signedIn,true);
  const gate=deferred();
  api.onRequest=async (entry,route,respond)=>{
    if(entry.pathname==='/api/auth/logout') { await gate.promise; api.signedIn=false; await respond(route,200,{ok:true}); return true; }
    return false;
  };
  await exit.click(); await dialog.getByRole('button',{name:'Salir'}).click();
  await page.waitForFunction(() => document.querySelector('.p-dialog .p-button-danger')?.disabled===true);
  assert.equal(await dialog.getByRole('button',{name:'Cancelar'}).isDisabled(),true,'Cancelar debe bloquearse mientras se confirma la salida');
  await page.keyboard.press('Escape');
  assert.equal(await dialog.isVisible(),true,'Escape no debe cerrar una confirmación pendiente');
  gate.resolve();
  await page.getByRole('heading',{name:'Ingresar a Libro de Trabajo'}).waitFor();
  assert.equal(await page.getByRole('heading',{name:'Avisos del equipo'}).count(),0);
  api.onRequest=null;
  await signIn(page,'Avisos del equipo'); await notices(page);
  api.onRequest=async (entry,route,respond)=>{
    if(entry.pathname==='/api/notices/page') {api.signedIn=false; await respond(route,401,{detail:'Sesión vencida'}); return true;}
    return false;
  };
  await page.getByRole('button',{name:'Aplicar filtros'}).click();
  await page.getByRole('heading',{name:'Ingresar a Libro de Trabajo'}).waitFor();
});

test('React real: fallo de carga anunciado y reintento', async t => {
  const {page,api}=await fixture(t); await signIn(page);
  let fail=true;
  api.onRequest=async (entry,route,respond)=>{
    if(entry.pathname==='/api/notices/page' && fail) {fail=false; await respond(route,503,{detail:'Servicio sintético no disponible'}); return true;}
    return false;
  };
  await page.locator('[data-page="notices"]').click();
  const alert=page.getByRole('alert').filter({hasText:'No se pudo cargar esta pantalla'});
  await alert.waitFor();
  assert.match(await alert.innerText(),/Servicio sintético no disponible/);
  await alert.getByRole('button',{name:'Reintentar'}).click();
  await page.locator('.notice-prime-table.p-datatable').waitFor();
});

test('Avisos: calendario español sin desborde y selectores alineados con estado abierto visible', async t => {
  const {page}=await fixture(t);
  await page.setViewportSize({width:1920,height:1080});
  await signIn(page);
  await notices(page);
  const view=page.locator('.notice-prime-view label').filter({hasText:'Vista'}).first().locator('.p-dropdown');
  await view.click();
  const selected=page.locator('.p-dropdown-panel:visible .p-dropdown-item.p-highlight');
  await selected.waitFor();
  assert.match(await selected.innerText(),/Activos/);
  const alignment=await selected.evaluate(item=>{
    const panel=item.closest('.p-dropdown-panel').getBoundingClientRect();
    const box=item.getBoundingClientRect();
    const range=document.createRange();range.selectNodeContents(item);
    const text=range.getBoundingClientRect();
    return {panelLeft:panel.left,panelRight:panel.right,left:box.left,right:box.right,textLeft:text.left,textRight:text.right};
  });
  assert.ok(alignment.left>=alignment.panelLeft && alignment.right<=alignment.panelRight+1,'El resaltado queda dentro del panel');
  assert.ok(alignment.textLeft>=alignment.left+8 && alignment.textRight<=alignment.right,'El texto queda contenido y centrado en el resaltado');
  await page.keyboard.press('Escape');
  assert.match(await view.innerText(),/Activos/);

  for(const label of ['Desde','Hasta']){
    await page.locator('.notice-prime-view label').filter({hasText:label}).first().locator('.p-datepicker-trigger').click();
    const calendar=page.locator('.p-datepicker:visible').last();
    await calendar.waitFor();
    const month=await calendar.locator('.p-datepicker-month').innerText();
    assert.match(month,/^(Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre)$/);
    const geometry=await calendar.evaluate(panel=>{
      const table=panel.querySelector('.p-datepicker-calendar');
      const headers=[...table.querySelectorAll('thead th')];
      const days=[...table.querySelectorAll('tbody tr:first-child td')];
      const rect=panel.getBoundingClientRect();
      return {count:headers.length,labels:headers.map(item=>item.innerText.trim()),layout:getComputedStyle(table).tableLayout,widths:headers.map((item,index)=>({header:item.getBoundingClientRect().width,day:days[index]?.getBoundingClientRect().width,centerDelta:Math.abs((item.getBoundingClientRect().left+item.getBoundingClientRect().right-days[index]?.getBoundingClientRect().left-days[index]?.getBoundingClientRect().right)/2),headerAlign:getComputedStyle(item).textAlign,dayAlign:getComputedStyle(days[index]).textAlign})),right:headers.at(-1)?.getBoundingClientRect().right,panelRight:rect.right,tableRight:table.getBoundingClientRect().right};
    });
    assert.equal(geometry.count,7,'La semana tiene siete columnas');
    assert.deepEqual(geometry.labels,['LU','MA','MI','JU','VI','SA','DO']);
    assert.equal(geometry.layout,'fixed','El calendario distribuye las columnas con table-layout fixed');
    assert.ok(geometry.widths.every(({header,day,centerDelta})=>Math.abs(header-day)<1 && centerDelta<1),'Cabeceras y fechas comparten el mismo ancho y centro');
    assert.ok(geometry.widths.every(({headerAlign,dayAlign})=>headerAlign==='center' && dayAlign==='center'),'Cabeceras y fechas centran su contenido');
    assert.ok(geometry.right<=geometry.panelRight+1 && geometry.tableRight<=geometry.panelRight+1,'El sábado y la tabla quedan dentro del popup');
    if(label==='Desde' && process.env.VISUAL_OUTPUT){fs.mkdirSync(process.env.VISUAL_OUTPUT,{recursive:true});await page.screenshot({path:path.join(process.env.VISUAL_OUTPUT,'avisos-calendario-es-1920.png'),fullPage:true});}
    if(label==='Desde'){
      const months=['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
      const start=months.indexOf(month);
      for(let offset=1;offset<12;offset++){
        await calendar.locator('.p-datepicker-next').click();
        assert.equal(await calendar.locator('.p-datepicker-month').innerText(),months[(start+offset)%12],'Cada mes conserva su inicial mayúscula');
      }
    }
    await page.keyboard.press('Escape');
  }

  const status=page.locator('.notice-prime-table tbody tr').first().locator('.p-dropdown');
  const closedBorder=await status.evaluate(node=>getComputedStyle(node).borderColor);
  const closedBackground=await status.evaluate(node=>getComputedStyle(node).backgroundColor);
  const closedShadow=await status.evaluate(node=>getComputedStyle(node).boxShadow);
  await status.click();
  await page.locator('.p-dropdown-panel:visible').waitFor();
  assert.equal(await status.locator('.p-dropdown-trigger').getAttribute('aria-expanded'),'true');
  const openShadow=await status.evaluate(node=>getComputedStyle(node).boxShadow);
  const openBorder=await status.evaluate(node=>getComputedStyle(node).borderColor);
  const openBackground=await status.evaluate(node=>getComputedStyle(node).backgroundColor);
  assert.notEqual(openShadow,closedShadow,'El estado abierto resalta el trigger');
  assert.notEqual(openBorder,closedBorder,'El borde primario aparece solo al abrir el estado');
  assert.equal(openBorder,'rgb(59, 130, 246)','El borde abierto usa azul 500');
  assert.notEqual(openBackground,closedBackground,'El selector abierto también cambia su superficie');
  if(process.env.VISUAL_OUTPUT) await page.screenshot({path:path.join(process.env.VISUAL_OUTPUT,'avisos-estado-abierto-1920.png'),fullPage:true});
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>document.querySelector('.notice-prime-table tbody tr .p-dropdown-trigger')?.getAttribute('aria-expanded')==='false');
  await page.waitForFunction(()=>!document.querySelector('.notice-prime-table tbody tr .p-dropdown')?.classList.contains('tw-ring-2'));
  assert.equal(await status.evaluate(node=>node.classList.contains('tw-ring-2')),false,'El anillo de menú abierto se retira al cerrar');
  await page.getByRole('heading',{name:'Avisos del equipo'}).click();
  assert.equal(await status.evaluate(node=>getComputedStyle(node).boxShadow),closedShadow,'El foco conserva su indicador solo mientras corresponde');
  assert.equal(await status.evaluate(node=>getComputedStyle(node).borderColor),closedBorder,'El borde vuelve a su color original al cerrar');
  const secondStatus=page.locator('.notice-prime-table tbody tr').nth(1).locator('.p-dropdown');
  await secondStatus.click();
  await page.locator('.p-dropdown-panel:visible').waitFor();
  assert.equal(await secondStatus.evaluate(node=>getComputedStyle(node).borderColor),'rgb(59, 130, 246)','Cada fila maneja su propio estado abierto');
  assert.equal(await status.evaluate(node=>node.classList.contains('tw-ring-2')),false,'Abrir otra fila no resalta la anterior');
  await page.keyboard.press('Escape');
});

test('React real: un clic muestra los tres servicios y todas las franjas sin selectores', async t => {
  const {page,api}=await fixture(t);
  await signIn(page);
  assert.equal(await page.locator('path.map-department').first().getAttribute('fill'),'#dbeafe');
  await page.locator('path.map-department').first().click();
  const panel=page.getByRole('complementary',{name:'Consulta de llegada'});
  await panel.getByRole('heading',{name:'Montevideo'}).waitFor();
  await panel.getByRole('region',{name:'Grúa'}).getByText('75 min habituales').waitFor();
  await panel.getByRole('region',{name:'Mecánica Ligera'}).getByText('40 min habituales').waitFor();
  await panel.getByRole('region',{name:'Siniestros'}).getByText('Sin estándar configurado').waitFor();
  assert.equal(await panel.locator('.p-dropdown').count(),0);
  assert.equal(await panel.getByRole('button',{name:/detalle de/i}).count(),0);
  assert.equal(api.requests.filter(entry=>entry.pathname==='/api/arrival-times/overview').length,1);
  assert.equal(api.requests.some(entry=>entry.pathname==='/api/arrival-times/department'),false);
  assert.equal(await page.getByText('Alertas operativas').count(),0);
  assert.equal(await page.getByRole('button',{name:'Asignadas a mí'}).count(),0);
  assert.equal(api.requests.some(entry=>entry.pathname==='/api/operational-alerts'),false);
  const visualOutput=process.env.VISUAL_OUTPUT;
  if(visualOutput){fs.mkdirSync(visualOutput,{recursive:true});await page.setViewportSize({width:1920,height:1080});await page.screenshot({path:path.join(visualOutput,'resumen-consulta-1920.png'),fullPage:true});}
});

test('React real: máximos, intervalos y confirmación se leen juntos sin elegir zona', async t => {
  const {page,api}=await fixture(t);
  api.arrivalItems=[
    {id:21,service:'ML',department:'MONTEVIDEO',zone:'Pocitos, Buceo',zone_members:['Pocitos','Buceo'],indication_type:'MAXIMUM',minutes_max:30},
    {id:22,service:'SINIESTROS',department:'MONTEVIDEO',zone:'Pocitos',zone_members:['Pocitos'],indication_type:'INTERVAL',minutes_min:30,minutes_max:45},
    {id:23,service:'GRÚA',department:'MONTEVIDEO',zone:'Todo el departamento',zone_members:[],indication_type:'TO_CONFIRM'},
  ];
  await signIn(page);
  await page.locator('path.map-department').first().click();
  const panel=page.getByRole('complementary',{name:'Consulta de llegada'});
  await panel.getByRole('region',{name:'Mecánica Ligera'}).getByText('Máximo de 30 min').waitFor();
  await panel.getByRole('region',{name:'Siniestros'}).getByText('Entre 30 y 45 min').waitFor();
  await panel.getByRole('region',{name:'Grúa'}).getByText('A confirmar',{exact:true}).last().waitFor();
  assert.equal(await panel.locator('.p-dropdown,.delay-map-overlay,.p-sidebar').count(),0);
});

test('React real: una demora de GRÚA no altera otras prestaciones y TODAS sí las alcanza', async t => {
  const {page,api}=await fixture(t);
  api.arrivalItems.push({id:25,service:'SINIESTROS',department:'MONTEVIDEO',zone:'Todo el departamento',base_estimated_minutes:90,revision:1});
  let delay={id:301,service:'GRÚA',zone:'Pocitos',message:'No confirmar tiempos',review_due_at:'2099-01-01T00:00:00Z'};
  api.onRequest=async(entry,route,respond)=>{
    if(entry.pathname!=='/api/dashboard/map-stats')return false;
    await respond(route,200,{as_of:'2026-10-16T12:00:00Z',departments:[{department:'MONTEVIDEO',delays:[delay],active_count:1,verified_count:1,review_due_count:0}]});
    return true;
  };
  await signIn(page);
  await page.waitForFunction(()=>document.querySelector('path.map-department')?.getAttribute('fill')==='#ef4444');
  await page.locator('path.map-department').first().click();
  const panel=page.getByRole('complementary',{name:'Consulta de llegada'});
  await panel.getByRole('region',{name:'Grúa'}).getByText('Demora activa: No confirmar tiempos').waitFor();
  await panel.getByRole('region',{name:'Mecánica Ligera'}).getByText('40 min habituales').waitFor();
  await panel.getByRole('region',{name:'Siniestros'}).getByText('90 min habituales').waitFor();
  delay={...delay,service:'TODAS'};
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('libro:operational-change',{detail:{url:'/api/delays/301',method:'PATCH'}})));
  await panel.getByRole('region',{name:'Mecánica Ligera'}).getByText('Demora activa: No confirmar tiempos').waitFor();
  await panel.getByRole('region',{name:'Siniestros'}).getByText('Demora activa: No confirmar tiempos').waitFor();
  assert.equal(await panel.locator('.p-dropdown').count(),0);
});

test('React real: Configuración muestra los campos correctos para intervalo y A confirmar', async t => {
  const {page,api}=await fixture(t);
  api.actor={...actor,role_name:'Planificador',permissions:['dashboard.view','standards.view','arrival_times.manage']};
  await signIn(page);
  await page.locator('[data-page="settings"]').click();
  await page.getByRole('button',{name:'Nuevo tiempo'}).click();
  const editor=page.getByRole('dialog',{name:'Nuevo tiempo estándar'});
  await editor.locator('label').filter({hasText:'Indicación'}).locator('.p-dropdown').click();
  await page.getByRole('option',{name:'Entre (intervalo)'}).click();
  await editor.getByText('Desde (minutos)').waitFor();
  await editor.getByText('Hasta (minutos)').waitFor();
  assert.equal(await editor.getByText('Tiempo habitual (minutos)').count(),0);
  await editor.locator('label').filter({hasText:'Indicación'}).locator('.p-dropdown').click();
  await page.getByRole('option',{name:'A confirmar'}).click();
  await editor.getByText('No se comunicará un tiempo numérico: A confirmar.').waitFor();
  assert.equal(await editor.locator('input.p-inputnumber-input').count(),0);
});

test('React real: cambio de departamento y actualización de referencias sin segundo clic', async t => {
  const {page,api}=await fixture(t);
  api.onRequest=async(entry,route,respond)=>{
    if(entry.pathname==='/api/arrival-times/overview') {
      await respond(route,200,{departments:{MONTEVIDEO:api.arrivalItems,CANELONES:[{id:11,service:'GRÚA',zone:'Ciudad de la Costa',indication_type:'MAXIMUM',minutes_max:45}]}});
      return true;
    }
    return false;
  };
  await signIn(page);
  const departments=page.locator('path.map-department');
  await departments.first().focus(); await departments.first().press('Enter');
  const panel=page.getByRole('complementary',{name:'Consulta de llegada'});
  await panel.getByRole('heading',{name:'Montevideo'}).waitFor();
  await panel.getByRole('region',{name:'Mecánica Ligera'}).getByText('Pocitos').waitFor();
  api.arrivalItems=api.arrivalItems.map(item=>item.service==='GRÚA'?{...item,base_estimated_minutes:85,revision:2}:item);
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('libro:operational-change',{detail:{url:'/api/arrival-times/4',method:'PATCH'}})));
  await panel.getByRole('region',{name:'Grúa'}).getByText('85 min habituales').waitFor();
  await departments.nth(1).click();
  await panel.getByRole('heading',{name:'Canelones'}).waitFor();
  await panel.getByRole('region',{name:'Grúa'}).getByText('Máximo de 45 min').waitFor();
  assert.equal(await panel.getByText('Pocitos').count(),0);
  assert.equal(await panel.locator('.p-dropdown').count(),0);
});

test('React real: solapamiento, revisión, error y normalización no inventan tiempo', async t => {
  const {page,api}=await fixture(t);
  const base={as_of:'2026-10-14T10:00:00-03:00',departments:[{department:'MONTEVIDEO',active_count:2,verified_count:2,review_due_count:0,delays:[
    {id:201,service:'TODAS',zone:'Todo el departamento',message:'No confirmar tiempos',review_due_at:'2099-01-01T10:00:00Z',overlap_ids:[202]},
    {id:202,service:'ML',zone:'Pocitos',message:'Margen de',minutes:25,review_due_at:'2099-01-01T10:00:00Z',overlap_ids:[201]},
  ]}]};
  let snapshot=base,fail=false,failStandard=false;
  api.onRequest=async(entry,route,respond)=>{
    if(entry.pathname==='/api/dashboard/map-stats') {
      await respond(route,fail?503:200,fail?{detail:'Consulta sintética fallida'}:snapshot);
      return true;
    }
    if(entry.pathname==='/api/arrival-times/overview' && failStandard) {
      await respond(route,503,{detail:'Referencia sintética no disponible'});
      return true;
    }
    return false;
  };
  await signIn(page);
  await page.locator('path.map-department').first().click();
  const panel=page.getByRole('complementary',{name:'Consulta de llegada'});
  const ml=panel.getByRole('region',{name:'Mecánica Ligera'});
  await ml.getByText(/Demoras superpuestas · confirmar con Planificación/).waitFor();
  await ml.getByText(/No confirmar tiempos/).first().waitFor();
  assert.equal(await ml.getByText('40 min habituales').count(),0);
  assert.equal(await panel.locator('.p-dropdown').count(),0);
  snapshot={...base,departments:[{...base.departments[0],delays:base.departments[0].delays.map(item=>item.id===202?{...item,review_due_at:'2020-01-01T10:00:00Z'}:item)}]};
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('libro:operational-change',{detail:{url:'/api/delays/202/verify',method:'PATCH'}})));
  await ml.getByText(/Demoras superpuestas · confirmar con Planificación/).waitFor();
  await page.waitForFunction(()=>document.querySelector('path.map-department')?.getAttribute('fill')==='#b91c1c');
  fail=true;
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('libro:operational-change',{detail:{url:'/api/delays/202/verify',method:'PATCH'}})));
  await panel.getByText(/No se pudieron confirmar las demoras actuales/).waitFor();
  await ml.getByText('Información no disponible').last().waitFor();
  fail=false;
  snapshot={...base,departments:[{...base.departments[0],delays:[{...base.departments[0].delays[0],overlap_ids:[]}]}]};
  await panel.getByRole('button',{name:'Reintentar',exact:true}).click();
  await ml.getByText('Demora activa: No confirmar tiempos').waitFor();
  snapshot={...base,departments:[{...base.departments[0],delays:[]}]};
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('libro:operational-change',{detail:{url:'/api/delays/201/normalize',method:'PATCH'}})));
  await ml.getByText('40 min habituales',{exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('path.map-department')?.getAttribute('fill')==='#dbeafe');
  assert.equal(await panel.locator('.p-dropdown').count(),0);
  failStandard=true;
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('libro:operational-change',{detail:{url:'/api/arrival-times/2',method:'PATCH'}})));
  await panel.getByText(/Referencia sintética no disponible/).waitFor();
  await ml.getByText('Información no disponible').last().waitFor();
});

test('React real: normalizar una demora es una acción directa y conserva el control de revisión', async t => {
  const {page,api}=await fixture(t);
  api.actor={...actor,permissions:[...actor.permissions,'delays.normalize']};
  let row={id:910,revision:3,service:'ML',department:'MONTEVIDEO',zone:'Pocitos',message:'Margen de',minutes:30,
    status:'VIGENTE',agent:'Planificador Sintético',created_at:'2026-10-14T10:00:00-03:00',
    next_review_at:'2099-01-01T10:00:00Z',needs_review:false,is_current:true};
  let patches=0;
  api.onRequest=async (entry,route,respond)=>{
    if(entry.pathname==='/api/delays'&&entry.method==='GET'){
      await respond(route,200,{items:[row],total:1,limit:50,offset:0});return true;
    }
    if(entry.pathname==='/api/delays/910/normalize'&&entry.method==='PATCH'){
      patches+=1;
      assert.deepEqual(entry.body,{expected_revision:3});
      row={...row,status:'NORMALIZADO',revision:4,normalized_at:'2026-10-14T11:00:00-03:00',normalized_by:'Planificador Sintético',is_current:false};
      await respond(route,200,row);return true;
    }
    return false;
  };
  await signIn(page);
  await page.locator('[data-page="delays"]').click();
  const table=page.locator('.delay-prime-table');
  await table.getByText('Margen: 30 min').waitFor();
  assert.equal(await table.getByRole('columnheader',{name:'Tiempo / indicación'}).count(),1);
  await table.getByRole('button',{name:'Normalizar'}).click();
  await table.getByText('Histórica / normalizada').waitFor();
  assert.equal(patches,1);
  assert.equal(await page.getByRole('dialog',{name:/normaliz/i}).count(),0);
  assert.equal(await table.getByRole('button',{name:'Normalizar'}).count(),0);
});

test('Sistema visual: escala, ancho útil, menús y tema en tres tamaños de escritorio', async t => {
  const {page}=await fixture(t);
  await page.setViewportSize({width:1920,height:1080});
  await page.unroute('**/uruguay-departamentos.geojson');
  await signIn(page);
  const assertLayout=async(label,expectedTitle=22)=>{
    const metrics=await page.evaluate(()=>({
      viewport:document.documentElement.clientWidth,
      document:document.documentElement.scrollWidth,
      title:parseFloat(getComputedStyle(document.querySelector('#prime-react-root h1')).fontSize),
      control:document.querySelector('#prime-react-root .p-button') ? parseFloat(getComputedStyle(document.querySelector('#prime-react-root .p-button')).minHeight) : null,
    }));
    assert.ok(metrics.document<=metrics.viewport+2,`${label}: desborde horizontal ${JSON.stringify(metrics)}`);
    assert.equal(metrics.title,expectedTitle,`${label}: título`);
    if(metrics.control!==null)assert.ok(metrics.control>=36,`${label}: controles de escritorio`);
  };
  await assertLayout('Resumen 1920');
  await page.locator('path.map-department[aria-label^="Montevideo:"]').click();
  await page.getByRole('complementary',{name:'Consulta de llegada'}).getByRole('heading',{name:'Montevideo'}).waitFor();
  if(process.env.VISUAL_OUTPUT)await page.screenshot({path:path.join(process.env.VISUAL_OUTPUT,'resumen-mapa-real-1920.png'),fullPage:true});
  await page.setViewportSize({width:1024,height:768});
  await assertLayout('Resumen 1024');
  const narrowMap=await page.locator('.uruguay-map-wrap').first().boundingBox();
  const narrowPanel=await page.getByRole('complementary',{name:'Consulta de llegada'}).boundingBox();
  assert.ok(narrowPanel.y>=narrowMap.y+narrowMap.height,'La consulta pasa debajo del mapa en una ventana estrecha');
  await page.setViewportSize({width:1920,height:1080});
  await notices(page);
  await assertLayout('Avisos 1920');
  const table=page.locator('.notice-prime-table');
  const headerSize=await table.locator('thead th').first().evaluate(node=>parseFloat(getComputedStyle(node).fontSize));
  const cellSize=await table.locator('tbody td').first().evaluate(node=>parseFloat(getComputedStyle(node).fontSize));
  assert.ok(headerSize>=12 && cellSize>=13,'Las tablas mantienen etiquetas de 12 px y datos de 13 px');
  const firstRowHeight=await table.locator('tbody tr').first().evaluate(node=>node.getBoundingClientRect().height);
  assert.ok(firstRowHeight>=36,'La fila puede crecer cuando el contenido lo necesita');
  await page.locator('.notice-prime-view .p-dropdown').first().click();
  const dropdown=page.locator('.p-dropdown-panel:visible');
  await dropdown.waitFor();
  const menuHeight=await dropdown.locator('.p-dropdown-items-wrapper').evaluate(node=>parseFloat(getComputedStyle(node).maxHeight));
  assert.ok(menuHeight>=240 && menuHeight<=280,'El menú largo usa una altura máxima, no obligatoria');
  await page.keyboard.press('Escape');
  const visualOutput=process.env.VISUAL_OUTPUT;
  if(visualOutput){fs.mkdirSync(visualOutput,{recursive:true});await page.screenshot({path:path.join(visualOutput,'avisos-1920.png'),fullPage:true});}
  await page.setViewportSize({width:1536,height:864});
  await assertLayout('Avisos 1536');
  await page.setViewportSize({width:1280,height:720});
  await assertLayout('Avisos 1280');
  await page.locator('.user-button').click();
  await page.getByRole('combobox',{name:'Cambiar tema visual'}).selectOption('dark');
  await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('.notice-prime-view input.p-inputtext')).backgroundColor==='rgb(15, 23, 42)');
  const dark=await page.evaluate(()=>({surface:getComputedStyle(document.querySelector('.notice-prime-table-card')).backgroundColor,
    text:getComputedStyle(document.querySelector('.notice-prime-table-card')).color,
    inputBackground:getComputedStyle(document.querySelector('.notice-prime-view input.p-inputtext')).backgroundColor,
    inputText:getComputedStyle(document.querySelector('.notice-prime-view input.p-inputtext')).color,
    dropdownBackground:getComputedStyle(document.querySelector('.notice-prime-view .p-dropdown')).backgroundColor,
    dropdownText:getComputedStyle(document.querySelector('.notice-prime-view .p-dropdown-label')).color}));
  assert.notEqual(dark.surface,dark.text,'El tema oscuro distingue superficie y texto');
  assert.equal(dark.inputBackground,'rgb(15, 23, 42)','Los campos oscuros no conservan el fondo blanco');
  assert.equal(dark.inputText,'rgb(248, 250, 252)','El texto del campo es claro');
  assert.equal(dark.dropdownBackground,'rgb(15, 23, 42)','Los selectores oscuros no conservan el fondo blanco');
  assert.ok(Number(dark.dropdownText.match(/\d+/)[0])>=150,'El valor seleccionado es legible');
  await assertLayout('Avisos oscuro 1280');
  if(visualOutput)await page.screenshot({path:path.join(visualOutput,'avisos-oscuro-1280.png'),fullPage:true});
  await page.locator('.user-button').click();
  await page.evaluate(()=>{document.body.style.zoom='1.25';});
  const zoomed=await page.evaluate(()=>({viewport:document.documentElement.clientWidth,document:document.documentElement.scrollWidth}));
  assert.ok(zoomed.document<=zoomed.viewport+2,`Avisos con ampliación: ${JSON.stringify(zoomed)}`);
});

test('Sistema visual: módulos operativos y de supervisión con estados vacíos', async t => {
  const {page,api}=await fixture(t);
  api.actor={...actor,permissions:[...actor.permissions,'quotes.view','quotes.create','transfers.view','transfers.create','transfers.manage','schedules.view','settings.manage','audit.view','reports.export','delays.create','delays.normalize']};
  await page.setViewportSize({width:1920,height:1080});
  await signIn(page);
  const visit=async(target,title)=>{
    await page.locator(`[data-page="${target}"]`).click();
    await page.getByRole('heading',{name:title,exact:true}).waitFor();
    try { await page.waitForFunction(view=>Boolean(document.querySelector(`[data-view="${view}"] .p-card`)) || Boolean(document.querySelector(`[data-view="${view}"] .p-datatable`)),target); }
    catch(error) { if(process.env.VISUAL_OUTPUT)await page.screenshot({path:path.join(process.env.VISUAL_OUTPUT,`${target}-failure.png`),fullPage:true}); throw new Error(`${title}: ${error.message}; alertas: ${await page.locator('[role="alert"]').allInnerTexts()}; peticiones: ${api.requests.slice(-4).map(entry=>entry.pathname).join(', ')}`); }
    const size=await page.evaluate(()=>({viewport:document.documentElement.clientWidth,width:document.documentElement.scrollWidth}));
    assert.ok(size.width<=size.viewport+2,`${title} desborda: ${JSON.stringify(size)}`);
    assert.equal(await page.locator('[role="alert"]').filter({hasText:'No se pudo cargar esta pantalla'}).count(),0,`${title} debe montar React`);
    if(process.env.VISUAL_OUTPUT)await page.screenshot({path:path.join(process.env.VISUAL_OUTPUT,`${target}-1920.png`),fullPage:true});
    await page.setViewportSize({width:1280,height:720});
    const narrow=await page.evaluate(()=>({viewport:document.documentElement.clientWidth,width:document.documentElement.scrollWidth}));
    assert.ok(narrow.width<=narrow.viewport+2,`${title} desborda a 1280 px: ${JSON.stringify(narrow)}`);
    await page.setViewportSize({width:1920,height:1080});
  };
  await visit('quotes','Cotizador de servicios');
  await page.getByRole('button',{name:'Manual por kilómetros'}).click();
  await page.getByRole('button',{name:'Calcular cotización manual'}).waitFor();
  await visit('delays','Zonas con demora');
  await page.locator('.delay-prime-toolbar .p-calendar .p-datepicker-trigger').first().click();
  await page.locator('.p-datepicker:visible').waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Registrar demora'}).click();
  const delayDialog=page.getByRole('dialog',{name:'Registrar demora vigente'});
  await delayDialog.waitFor();
  assert.ok(await delayDialog.evaluate(node=>node.getBoundingClientRect().width)<=640,'Formulario habitual dentro de 640 px');
  assert.equal(await delayDialog.locator('input[aria-label="Prestación afectada"]').count(),1,'El selector de prestación tiene nombre accesible');
  await delayDialog.locator('.p-dropdown').first().click();
  await page.locator('.p-dropdown-panel:visible').waitFor();
  await page.keyboard.press('Escape');
  if(await delayDialog.isVisible())await delayDialog.getByRole('button',{name:'Cancelar'}).click();
  await visit('transfers','Programados');
  await page.getByRole('button',{name:'Nuevo programado'}).click();
  await page.getByRole('dialog',{name:'Nuevo programado'}).waitFor();
  await page.keyboard.press('Escape');
  await visit('schedules','Horarios');
  await visit('requests','Mis solicitudes');
  await page.getByRole('button',{name:'Mis horarios'}).click();
  await page.getByText('Mi semana').waitFor();
  await page.locator('.sidebar-section-toggle').click();
  for(const [target,title] of [['supervision','Dashboard de Supervisión'],['delayAudit','Auditoría de demoras'],['wfm','Planificación de horarios'],['audit','Registro de auditoría'],['settings','Configuración']])await visit(target,title);
});

test('WFM muestra horas legibles y jerarquía visual en el editor de turnos', async t => {
  const {page, api} = await fixture(t);
  api.actor = {...actor, permissions:[...actor.permissions, 'schedules.view']};
  api.onRequest = async (entry, route, respond) => {
    if (entry.pathname !== '/api/wfm/plan') return false;
    await respond(route, 200, {revision:1, published_revision:0, window:[16,36],
      people:[{id:701, display_name:'Alejandra Ferreira'}],
      shifts:[{user_id:701, start:19, end:27, segments:[{start:19,end:27}], break:22,
        break_duration:1, overtime_slots:0, exceptions:[]}],
      demand:Array(48).fill(0), requirements:Array(7).fill(0), weekly_schedule:[], settings:{}});
    return true;
  };
  await signIn(page);
  await page.goto(`${baseUrl}/supervision/planificacion`);
  const dialog = page.getByRole('dialog', {name:'Editar turno y excepciones'});
  await page.getByRole('button', {name:'Editar', exact:true}).first().click();
  await dialog.waitFor();
  assert.match(await dialog.locator('.p-dropdown').nth(0).innerText(), /09:30/);
  assert.match(await dialog.locator('.p-dropdown').nth(1).innerText(), /13:30/);
  assert.match(await dialog.locator('.p-dropdown').nth(2).innerText(), /11:00/);
  const colors = await dialog.evaluate(node => ({
    header:getComputedStyle(node.querySelector('.p-dialog-header')).backgroundColor,
    content:getComputedStyle(node.querySelector('.p-dialog-content')).backgroundColor,
  }));
  assert.notEqual(colors.header, colors.content, 'El encabezado distingue visualmente el diálogo');
  await dialog.locator('.p-dropdown').first().click();
  await page.getByRole('option', {name:'10:00', exact:true}).click();
  await dialog.getByRole('button', {name:'Aplicar al borrador'}).click();
  assert.match(await page.locator('.wfm-react-view .p-datatable').first().innerText(), /10:00/);
});

test('Cotizador: orden, búsqueda inequívoca, base opcional y mapa adaptable', async t => {
  const {page,api}=await fixture(t);
  api.actor={...actor,permissions:[...actor.permissions,'quotes.view','quotes.create']};
  const transparentTile=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6SfgAAAAASUVORK5CYII=','base64');
  api.onRequest=async(entry,route,respond)=>{
    if(entry.pathname.startsWith('/api/tiles/')){await route.fulfill({status:200,contentType:'image/png',body:transparentTile});return true;}
    if(entry.pathname==='/api/quotes/resolve-location'){
      const [latitude,longitude]=entry.query.q.split(',').map(Number);
      await respond(route,200,{latitude,longitude,inside_uruguay:true});return true;
    }
    if(entry.pathname==='/api/quotes/geocode'){
      const q=entry.query.q;
      const locations=q.includes('Julio')
        ? [{label:'18 de Julio 1000, Montevideo, Montevideo, Uruguay',latitude:-34.9011,longitude:-56.1645,country_code:'UY'}]
        : [{label:'San Martín 100, Buenos Aires, Buenos Aires, Argentina',latitude:-34.6037,longitude:-58.3816,country_code:'AR'},
          {label:'San Martín 100, Rosario, Santa Fe, Argentina',latitude:-32.9468,longitude:-60.6393,country_code:'AR'}];
      await respond(route,200,locations);return true;
    }
    if(entry.pathname==='/api/quotes/calculate'){
      const body=entry.body,mobile=body.include_mobile?5:0;
      const trip={label:'Traslado: origen → destino',coordinates:[[-56.1645,-34.9011],[-56.15,-34.89]]};
      const segments=body.include_mobile?[trip,{label:'Salida de la grúa → origen del cliente',coordinates:[[-56.18,-34.91],[-56.1645,-34.9011]]}]:[trip];
      await respond(route,201,{id:77,task_number:body.task_number,origin_input:body.origin,destination_input:body.destination,mobile_input:body.mobile_origin,
        customer_type:'Asegurado',mode:'automatic',trip_km:10,mobile_km:mobile,total_km:10+mobile,included_km:25,extra_km:0,extra_rate:120,
        base_price:1000,extra_price:0,toll_count:0,toll_details:[],toll_price:0,total_price:47860,route_segments:segments});
      return true;
    }
  };
  await page.setViewportSize({width:1920,height:1080});
  await signIn(page);
  await page.locator('[data-page="quotes"]').click();
  await page.getByRole('heading',{name:'Cotizador de servicios'}).waitFor();
  const trip=page.locator('.quote-step-card').filter({hasText:'Recorrido de la grúa'});
  const labels=await trip.innerText();
  assert.ok(labels.indexOf('1 · Origen del servicio')<labels.indexOf('2 · Destino del servicio'));
  assert.ok(labels.indexOf('2 · Destino del servicio')<labels.indexOf('3 · Salida de la grúa'));
  await page.getByLabel('Número de tarea (opcional)').fill('001000');
  await page.getByLabel('Punto de recogida').pressSequentially('San Martín 100',{delay:20});
  await page.getByRole('option',{name:/Rosario, Santa Fe, Argentina/}).click();
  assert.equal(api.requests.filter(entry=>entry.pathname==='/api/quotes/geocode').length,1,'La búsqueda espera el fin de la escritura');
  await page.getByLabel('Punto de entrega').fill('-34.890000, -56.150000');
  await page.getByRole('button',{name:'Trazar recorrido y calcular'}).click();
  await page.getByText(/No hay tarifa regional configurada/).waitFor();
  assert.equal(api.requests.filter(entry=>entry.pathname==='/api/quotes/calculate').length,0);
  await page.getByLabel('Punto de recogida').fill('18 de Julio 1000');
  await page.getByRole('option',{name:/Montevideo, Montevideo, Uruguay/}).click();
  const destination=page.getByLabel('Punto de entrega').locator('..');
  await destination.getByRole('button',{name:'Coordenadas o enlace'}).click();
  await page.getByLabel('Punto de entrega').fill('-34.890000, -56.150000');
  await destination.getByRole('button',{name:'Ver punto en el mapa'}).click();
  await destination.getByRole('button',{name:'Confirmar este punto'}).click();
  await page.getByRole('button',{name:'Trazar recorrido y calcular'}).click();
  await page.getByText('$ 47.860,00').first().waitFor();
  assert.match(await page.locator('.quote-result-card').innerText(),/\$ 1\.000/);
  assert.match(await page.locator('.quote-result-card').innerText(),/001000/);
  const firstPost=api.requests.find(entry=>entry.pathname==='/api/quotes/calculate');
  assert.equal(firstPost.body.task_number,'001000');
  assert.equal(firstPost.body.include_mobile,false);
  assert.equal(firstPost.body.mobile_origin,null);
  const wide=await page.evaluate(()=>({form:document.querySelector('.quote-form-panel').getBoundingClientRect().width,result:document.querySelector('.quote-result-card').getBoundingClientRect().width,map:document.querySelector('#quote-map').getBoundingClientRect().height,overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth}));
  assert.ok(wide.result>wide.form*1.15,JSON.stringify(wide));
  assert.ok(wide.map>=360,JSON.stringify(wide));
  assert.ok(wide.overflow<=2,JSON.stringify(wide));
  await page.setViewportSize({width:1000,height:800});
  const narrow=await page.evaluate(()=>({form:document.querySelector('.quote-form-panel').getBoundingClientRect(),result:document.querySelector('.quote-result-card').getBoundingClientRect(),overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth}));
  assert.ok(narrow.result.top>=narrow.form.bottom-2,'Formulario y resultado se apilan');
  assert.ok(narrow.overflow<=2,JSON.stringify({overflow:narrow.overflow}));
  await page.getByText('Incluir desplazamiento desde la base').click();
  const base=page.getByLabel('Ubicación de la base').locator('..');
  await base.getByRole('button',{name:'Coordenadas o enlace'}).click();
  await page.getByLabel('Ubicación de la base').fill('-34.910000, -56.180000');
  await base.getByRole('button',{name:'Ver punto en el mapa'}).click();
  await base.getByRole('button',{name:'Confirmar este punto'}).click();
  await page.getByRole('button',{name:'Trazar recorrido y calcular'}).click();
  await page.getByText('15.00 km', {exact:false}).first().waitFor();
  const posts=api.requests.filter(entry=>entry.pathname==='/api/quotes/calculate');
  assert.equal(posts.length,2);
  assert.equal(posts[1].body.include_mobile,true);
  assert.equal(posts[1].body.mobile_origin,'-34.910000, -56.180000');
  const origin=page.getByLabel('Punto de recogida').locator('..');
  await origin.getByRole('button',{name:'Coordenadas o enlace'}).click();
  assert.equal(await page.getByLabel('Punto de recogida').inputValue(),'','Cambiar de modo borra el punto anterior');
  await page.getByLabel('Punto de recogida').fill('-34.813803, -55.238921');
  await page.getByRole('button',{name:'Trazar recorrido y calcular'}).click();
  await page.getByText(/Confirmá cada punto/).waitFor();
  assert.equal(api.requests.filter(entry=>entry.pathname==='/api/quotes/calculate').length,2);
  await origin.getByRole('button',{name:'Ver punto en el mapa'}).click();
  await origin.getByRole('img',{name:/Punto interpretado/}).waitFor();
  await origin.getByRole('button',{name:'Confirmar este punto'}).click();
  await page.getByLabel('Punto de recogida').fill('-34.813804, -55.238922');
  await page.getByRole('button',{name:'Trazar recorrido y calcular'}).click();
  await page.getByText(/Confirmá cada punto/).waitFor();
  assert.equal(api.requests.filter(entry=>entry.pathname==='/api/quotes/calculate').length,2,'Editar un punto confirmado lo invalida');
});

test('Cotizador: una búsqueda anterior no reemplaza sugerencias nuevas', async t => {
  const {page,api}=await fixture(t);
  api.actor={...actor,permissions:[...actor.permissions,'quotes.view','quotes.create']};
  const old=deferred();
  api.onRequest=async(entry,route,respond)=>{
    if(entry.pathname!=='/api/quotes/geocode')return false;
    if(entry.query.q.includes('Vieja')){
      await old.promise;
      try{await respond(route,200,[{label:'Calle Vieja, Montevideo, Uruguay',latitude:-34.9,longitude:-56.16,country_code:'UY'}]);}catch{}
      return true;
    }
    await respond(route,200,[{label:'Calle Nueva, Canelones, Uruguay',latitude:-34.8,longitude:-56.1,country_code:'UY'}]);
    return true;
  };
  await signIn(page);
  await page.locator('[data-page="quotes"]').click();
  await page.getByLabel('Punto de recogida').fill('Calle Vieja');
  await until(()=>api.requests.some(entry=>entry.pathname==='/api/quotes/geocode'&&entry.query.q==='Calle Vieja'),'La primera búsqueda no salió');
  await page.getByLabel('Punto de recogida').fill('Calle Nueva');
  await page.getByRole('option',{name:/Calle Nueva, Canelones/}).waitFor();
  old.resolve();
  await new Promise(resolve=>setTimeout(resolve,100));
  assert.equal(await page.getByRole('option',{name:/Calle Vieja/}).count(),0);
});

test('Cotizador: distingue sin resultados, búsqueda no configurada y proveedor caído', async t => {
  const {page,api}=await fixture(t);
  api.actor={...actor,permissions:[...actor.permissions,'quotes.view','quotes.create']};
  api.onRequest=async(entry,route,respond)=>{
    if(entry.pathname!=='/api/quotes/geocode')return false;
    if(entry.query.q==='SinResultado')await respond(route,200,[]);
    else if(entry.query.q==='SinConfig')await respond(route,503,{detail:'La búsqueda requiere configurar GEOCODER_URL'});
    else await respond(route,503,{detail:'El servicio externo no respondió'});
    return true;
  };
  await signIn(page);
  await page.locator('[data-page="quotes"]').click();
  const input=page.getByLabel('Punto de recogida');
  await input.fill('SinResultado');
  await page.getByText(/Sin resultados/).waitFor();
  await input.fill('SinConfig');
  await page.getByText(/Falta configurar la búsqueda/).waitFor();
  await input.fill('NoDisponible');
  await page.getByText(/proveedor de direcciones no está disponible/).waitFor();
  assert.ok(api.requests.filter(entry=>entry.pathname==='/api/quotes/geocode').every(entry=>entry.query.country==='UY'));
});

test('Cotizador: confirma enlace de Maps regional y borra el punto al cambiar de método', async t => {
  const {page,api}=await fixture(t);
  api.actor={...actor,permissions:[...actor.permissions,'quotes.view','quotes.create']};
  const transparentTile=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6SfgAAAAASUVORK5CYII=','base64');
  api.onRequest=async(entry,route,respond)=>{
    if(entry.pathname.startsWith('/api/tiles/')){await route.fulfill({status:200,contentType:'image/png',body:transparentTile});return true;}
    if(entry.pathname==='/api/quotes/resolve-location'){
      assert.equal(entry.query.q,'https://www.google.com.ar/maps/place/ejemplo');
      await respond(route,200,{latitude:-34.9011,longitude:-56.1645,inside_uruguay:true});return true;
    }
    return false;
  };
  await signIn(page);
  await page.locator('[data-page="quotes"]').click();
  const origin=page.getByLabel('Punto de recogida').locator('..');
  await origin.getByRole('button',{name:'Coordenadas o enlace'}).click();
  await page.getByLabel('Punto de recogida').fill('https://www.google.com.ar/maps/place/ejemplo');
  await origin.getByRole('button',{name:'Ver punto en el mapa'}).click();
  await origin.getByRole('img',{name:/Punto interpretado/}).waitFor();
  await origin.getByRole('button',{name:'Confirmar este punto'}).click();
  assert.equal(await page.getByLabel('Punto de recogida').inputValue(),'-34.901100, -56.164500');
  await origin.getByRole('button',{name:'Buscar dirección'}).click();
  assert.equal(await page.getByLabel('Punto de recogida').inputValue(),'');
  assert.equal(await origin.getByText('Punto confirmado').count(),0);
});
