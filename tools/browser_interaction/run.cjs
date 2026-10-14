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
    if (url.pathname === '/') file = path.join(staticRoot, 'index.html');
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
  const state = {signedIn:false, notices:[firstNotice(), secondNotice()], requests:[],
    nextId:13, unexpected:[], onRequest:null, postCount:0, patchCount:0};
  const respond = (route, status, body) => route.fulfill({status, contentType:'application/json', body:JSON.stringify(body)});
  const handler = async route => {
    const request = route.request(), url = new URL(request.url()), pathname = url.pathname;
    const entry = {method:request.method(), pathname, query:Object.fromEntries(url.searchParams), body:request.postDataJSON?.()};
    state.requests.push(entry);
    if (state.onRequest && await state.onRequest(entry, route, respond)) return;
    if (pathname === '/api/auth/me') return respond(route, state.signedIn ? 200 : 401, state.signedIn ? actor : {detail:'Sesión requerida'});
    if (pathname === '/api/auth/login') { state.signedIn = true; return respond(route, 200, {ok:true}); }
    if (pathname === '/api/auth/logout') { state.signedIn = false; return respond(route, 200, {ok:true}); }
    if (!state.signedIn) return respond(route, 401, {detail:'Sesión requerida'});
    if (pathname === '/api/dashboard/map-stats') return respond(route, 200, {departments:[], updated_at:'2026-10-14T10:00:00-03:00'});
    if (pathname === '/api/operational-alerts') return respond(route, 200, []);
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
function respondGeo(route) { return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({type:'FeatureCollection',features:[]})}); }
async function signIn(page) {
  await page.getByRole('textbox',{name:'Usuario o correo electrónico'}).fill('operador.sintetico');
  await page.getByLabel('Contraseña',{exact:true}).fill('clave-de-prueba');
  await page.getByRole('button',{name:'Ingresar'}).click();
  await page.getByRole('heading',{name:'Resumen operativo'}).waitFor();
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

test('React real: login, navegación, filtro Enter, respuestas fuera de orden, vacío y textos largos', async t => {
  const {page,api} = await fixture(t);
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
  await signIn(page); await notices(page);
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
