const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const root = process.env.PROJECT_ROOT || '/project';
const staticRoot = path.join(root, 'app/static');
const actor = {id: 1, display_name: 'Agente de prueba', role_name: 'Telefonista', permissions: ['schedules.view']};
const day = (week, offset) => {
  const date = new Date(`${week}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
};
const snapshot = week => ({week, people: Array.from({length: 60}, (_, index) => ({
  id: index + 1, display_name: index ? `Compañero ${String(index).padStart(2, '0')}` : actor.display_name,
  role_name: 'Telefonista',
})), rows: [
  {id:'own', user_id:1, schedule_date:week, segments:[{start:16,end:20},{start:24,end:33}],
    start_slot:16,end_slot:33,break_slot:28,break_duration:1,overtime_slots:2,published_day:false},
  {id:'night', user_id:2, schedule_date:day(week, 1), segments:[{start:44,end:60}],
    start_slot:44,end_slot:60,break_slot:49,break_duration:1,overtime_slots:0,published_day:false},
  {id:'free', user_id:3, schedule_date:day(week, 2), segments:[],
    start_slot:null,end_slot:null,break_slot:null,break_duration:0,overtime_slots:0,published_day:true},
]});
let server, browser, base;
before(async () => {
  server = http.createServer((request, response) => {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    const file = path.join(staticRoot, pathname === '/' ? 'index.html' : pathname.replace(/^\/static\//, '').replace(/^\//, ''));
    if (!file.startsWith(staticRoot + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      response.writeHead(404); response.end(); return;
    }
    const type = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.woff2':'font/woff2'}[path.extname(file)] || 'application/octet-stream';
    response.writeHead(200, {'Content-Type': type, 'Cache-Control':'no-store'});
    fs.createReadStream(file).pipe(response);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({headless:true});
});
after(async () => { await browser?.close(); await new Promise(resolve => server?.close(resolve)); });

test('Equipo y Mis horarios conservan contenido y layout de consulta', async () => {
  const context = await browser.newContext({viewport:{width:1920,height:1080}});
  const page = await context.newPage();
  const errors = [], calls = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    calls.push(`${route.request().method()} ${url.pathname}`);
    const body = url.pathname === '/api/auth/me' ? actor
      : url.pathname === '/api/schedules/team' ? snapshot(url.searchParams.get('week'))
      : url.pathname === '/api/dashboard/map-stats' ? {departments:[], updated_at:new Date().toISOString()}
      : url.pathname === '/api/wfm/requests' ? [] : {};
    await route.fulfill({status:200, contentType:'application/json', body:JSON.stringify(body)});
  });
  await page.goto(base);
  await page.locator('[data-page="schedules"]').click();
  await page.getByRole('button', {name:'Mis horarios'}).waitFor();
  assert.equal(await page.locator('.p-datatable-tbody > tr').count(), 50);
  assert.match(await page.locator('.p-datatable').innerText(), /Compañero 01/);
  assert.match(await page.locator('.p-datatable').innerText(), /Libre publicado/);
  assert.match(await page.locator('.p-datatable').innerText(), /Sin publicación/);
  assert.match(await page.locator('.p-datatable').innerText(), /Descanso/);
  assert.match(await page.locator('.p-datatable').innerText(), /Extras/);
  assert.match(await page.locator('.p-datatable').innerText(), /Continúa del día anterior/);
  assert.equal(await page.getByRole('button', {name:/Editar|Publicar|Guardar/}).count(), 0);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.screenshot({path:path.join(root, 'artifacts/horarios-equipo-1920.png'), fullPage:true});
  await page.getByRole('textbox', {name:'Buscar compañero'}).fill('Compañero 01');
  assert.equal(await page.locator('.p-datatable-tbody > tr').count(), 1);
  await page.getByRole('textbox', {name:'Buscar compañero'}).fill('');
  await page.getByRole('button', {name:'Hoy'}).click();
  assert.equal(await page.locator('.p-datatable-thead th').count(), 2);
  await page.getByRole('button', {name:'Semana completa'}).click();
  assert.equal(await page.locator('.p-datatable-thead th').count(), 8);
  await page.setViewportSize({width:1366,height:768});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.equal(await page.locator('.p-datatable-wrapper').evaluate(node => node.scrollWidth > node.clientWidth), true);
  await page.setViewportSize({width:1920,height:1080});

  await page.getByRole('button', {name:'Mis horarios'}).click();
  await page.getByText('Mi semana').waitFor();
  assert.equal(await page.getByText('Sin publicación').count(), 6);
  assert.match(await page.locator('#content').innerText(), /Entrada 08:00/);
  assert.match(await page.locator('#content').innerText(), /Duración/);
  assert.equal(await page.locator('.p-datatable').count(), 0);
  await page.screenshot({path:path.join(root, 'artifacts/horarios-mios-1920.png'), fullPage:true});
  await page.getByRole('button', {name:'Hoy'}).click();
  assert.equal(await page.getByText('Sin publicación').count(), 1);
  await page.getByRole('button', {name:'Semana completa'}).click();

  await page.getByRole('button', {name:'Semana anterior'}).click();
  await page.getByText('Mi semana').waitFor();
  await page.locator('[data-page="requests"]').click();
  await page.getByRole('heading', {name:'Mis solicitudes'}).waitFor();
  assert.equal(calls.some(call => call.includes('/api/wfm/mine')), false);
  assert.equal(calls.some(call => call.includes('/api/schedules/team')), true);
  assert.deepEqual(errors, []);
  await context.close();
});
