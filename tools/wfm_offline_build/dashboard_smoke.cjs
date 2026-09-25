const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');

const projectRoot=path.resolve(__dirname,'../..');
const screenshotDir=process.env.UX_SCREENSHOT_DIR?path.resolve(process.env.UX_SCREENSHOT_DIR):null;
if(screenshotDir)fs.mkdirSync(screenshotDir,{recursive:true});

const dashboard={
 as_of:'2026-09-23T14:30:00-03:00',timezone:'America/Montevideo',definitions_version:'2',
 notices_open:7,delays_current:4,delays_need_review:1,transfers_pending:5,
 delay_metrics:{period_days:30,delays_created:18,delays_normalized:14,delay_verifications:31,delays_expiring_30m:1,average_resolution_minutes:42,verified_active_percentage:80,normalized_with_evidence_percentage:93,standards_overdue:2},
 distributions:{
  delays_by_department:[{department:'MONTEVIDEO',count:3,zones:['Centro','Pocitos']},{department:'CANELONES',count:1,zones:['Ciudad de la Costa']}],
  notices_by_status:{PENDIENTE:3,EN_GESTION:2,ESPERANDO_RESPUESTA:2},
  transfers_by_status:{SIN_ASIGNAR:2,ASIGNADO:2,EN_GESTION:1}
 }
};
const geo={type:'FeatureCollection',features:[
 {type:'Feature',properties:{nam:'MONTEVIDEO'},geometry:{type:'Polygon',coordinates:[[[-56.4,-35.0],[-56.0,-35.0],[-56.0,-34.7],[-56.4,-34.7],[-56.4,-35.0]]]}},
 {type:'Feature',properties:{nam:'CANELONES'},geometry:{type:'Polygon',coordinates:[[[-56.5,-34.7],[-55.7,-34.7],[-55.7,-34.2],[-56.5,-34.2],[-56.5,-34.7]]]}}
]};
const alerts=[
 {kind:'DELAY',severity:'OVERDUE',title:'Revisar demora en Centro',responsible:'Telefonista QA',due_at:'2026-09-23T14:20:00-03:00'},
 {kind:'STANDARD_APPROVAL',severity:'SOON',title:'Validar referencia de Ciudad de la Costa',responsible:'Planificador QA',due_at:'2026-09-23T15:00:00-03:00'}
];
const arrivalStandards=[
 {id:31,department:'MONTEVIDEO',service:'GRÚA',zone:'Centro y Ciudad Vieja con descripción operativa extensa',status:'SIN_REFERENCIA',approval_status:'APPROVED',availability:'REVIEW_DUE',review_due_at:'2026-09-20T10:00:00-03:00',owner:'Planificación Operativa Metropolitana',source:'Relevamiento interno',is_usable:false,minutes_min:30,minutes_max:45},
 {id:32,department:'MONTEVIDEO',service:'ML',zone:'Pocitos y Punta Carretas',status:'CONFIRMADO',approval_status:'APPROVED',availability:'CURRENT',owner:'Supervisor QA',source:'Histórico',is_usable:true,minutes_min:20,minutes_max:30},
 {id:33,department:'MONTEVIDEO',service:'SINIESTROS',zone:'Área metropolitana ampliada',status:'PROVISIONAL',approval_status:'PENDING',availability:'CURRENT',owner:'Planificador QA',source:'Propuesta',is_usable:false,minutes_min:40,minutes_max:55}
];
const arrivalCoverage=[{department:'MONTEVIDEO',service:'GRÚA',coverage:'PENDING'},{department:'MONTEVIDEO',service:'ML',coverage:'PENDING'},{department:'MONTEVIDEO',service:'SINIESTROS',coverage:'PENDING'}];
const arrivalZoneCoverage=[{zone:'Centro y Ciudad Vieja con descripción operativa extensa',service:'GRÚA',owner:'Planificación Operativa Metropolitana',coverage:'PENDING'}];

(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],messages=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>messages.push(`${message.type()}: ${message.text()}`));
  let html=fs.readFileSync(path.join(projectRoot,'app/static/index.html'),'utf8');
  html=html.replace(/<link\b[^>]*>/gi,'').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
  await page.route('http://dashboard.test/',route=>route.fulfill({status:200,contentType:'text/html',body:html}));
  await page.route('http://dashboard.test/static/frontend/**',route=>{
   const relative=decodeURIComponent(new URL(route.request().url()).pathname.replace('/static/frontend/',''));
   const file=path.join(projectRoot,'app/static/frontend',relative);
   const contentType=file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'application/octet-stream';
   route.fulfill({status:200,contentType,body:fs.readFileSync(file)});
  });
  await page.goto('http://dashboard.test/');
  for(const file of ['styles.css','settings.css','operations.css','dashboard.css','quotes.css','auth.css'])await page.addStyleTag({path:path.join(projectRoot,'app/static',file)});
  await page.addStyleTag({url:'http://dashboard.test/static/frontend/prime-react.css'});
  await page.evaluate(()=>{window.libroTrabajoUIReady=import('/static/frontend/prime-react.js')});
  await page.waitForFunction(()=>Boolean(window.LibroTrabajoUI));
  await page.addScriptTag({content:`window.fetch=async input=>{const url=String(input);if(url==='/api/auth/me')return new Promise(()=>{});let payload;if(url==='/uruguay-departamentos.geojson')return {ok:true,status:200,json:async()=>(${JSON.stringify(geo)})};if(url==='/api/dashboard')payload=${JSON.stringify(dashboard)};else if(url==='/api/operational-alerts')payload=${JSON.stringify(alerts)};else if(url==='/api/standards')payload=${JSON.stringify(arrivalStandards)};else if(url==='/api/settings/standards-coverage')payload=${JSON.stringify(arrivalCoverage)};else if(url.startsWith('/api/arrival-guidance?'))payload={active_delays:[],delays_needing_review:[],standards:${JSON.stringify(arrivalStandards)},operator_message:'Usar referencias vigentes'};else if(url.startsWith('/api/zones?'))payload=${JSON.stringify(arrivalStandards.map(row=>({name:row.zone})))};else if(url.startsWith('/api/zones-coverage?'))payload=${JSON.stringify(arrivalZoneCoverage)};else throw Error('Petición sintética no prevista: '+url);return {ok:true,status:200,text:async()=>JSON.stringify(payload)}};`});
  await page.addScriptTag({path:path.join(projectRoot,'app/static/app.js')});
  await page.evaluate(async()=>{authUser={id:99,display_name:'Operador QA',permissions:['dashboard.view','delays.view','standards.view','schedules.manage','audit.view','settings.manage']};currentUser=authUser.display_name;state.page='dashboard';await render()});
  if(await page.locator('#content').getAttribute('data-renderer')!=='prime-react')throw Error('Resumen no quedó montado con PrimeReact');
  if(await page.locator('.dashboard-prime-card.p-card').count()<8)throw Error('Faltan tarjetas PrimeReact en la jerarquía operativa');
  if(await page.locator('.dashboard-priority .p-tag').count()!==3)throw Error('Faltan las etiquetas PrimeReact de prioridad');
  const order=await page.locator('.dashboard-priority').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('aria-label')));
  if(order.join('|')!=='Mapa y demoras|Avisos operativos|Programados')throw Error(`Jerarquía incorrecta: ${order.join('|')} · contenido: ${await page.locator('#content').innerText()} · errores: ${errors.join(' | ')}`);
  if(!await page.locator('.dashboard-priority-one').getByText('Demoras verificadas por departamento',{exact:true}).count())throw Error('El mapa no está en prioridad 1');
  if(!await page.locator('.dashboard-priority-one').getByText('Departamentos afectados ahora',{exact:true}).count()||!await page.locator('.dashboard-priority-one').getByText('Estado de avisos abiertos',{exact:true}).count())throw Error('Las métricas inmediatas no están junto al mapa');
  if(!await page.locator('.dashboard-priority-two').getByText('Avisos que requieren gestión',{exact:true}).count()||!await page.locator('.dashboard-priority-two').getByText('Alertas operativas',{exact:true}).count())throw Error('La franja de avisos está incompleta');
  if(!await page.locator('.dashboard-priority-three').getByText('Programados pendientes',{exact:true}).count()||!await page.locator('.dashboard-priority-three').getByText('Estado de programados pendientes',{exact:true}).count())throw Error('La franja de programados está incompleta');
  const menuOrder=await page.locator('.sidebar-bottom').evaluate(node=>[...node.children].map(child=>child.matches('[data-supervision-menu]')?'Supervisión':child.textContent.trim()));
  if(menuOrder[0]!=='Supervisión'||menuOrder[1]!=='Configuración')throw Error(`Orden lateral incorrecto: ${menuOrder.join('|')}`);
  const expandedChevron=await page.locator('#supervision-toggle').evaluate(node=>getComputedStyle(node,'::after').content);
  if(!expandedChevron.includes('▸'))throw Error('El chevron no aparece a la derecha en el menú expandido');
  if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'resumen-escritorio.png'),fullPage:true});
  const themeButtons=page.locator('#theme-toggle-root [role="button"]');
  await page.waitForTimeout(100);
  const themeLabels=await themeButtons.allTextContents();
  if(themeLabels.join('|')!=='Sistema|Claro|Oscuro'){
   const diagnostics=await page.evaluate(()=>({root:document.querySelector('#theme-toggle-root')?.innerHTML,bridge:Object.keys(window.LibroTrabajoUI||{}),preference:document.documentElement.dataset.themePreference}));
   throw Error(`Selector de tema incompleto: ${themeLabels.join('|')} · ${JSON.stringify(diagnostics)} · ${messages.join(' | ')} · ${errors.join(' | ')}`);
  }
  if(await page.locator('#subtitle,.health').count())throw Error('El Header conserva información secundaria eliminada');
  await themeButtons.filter({hasText:'Claro'}).click();
  await page.waitForFunction(()=>document.documentElement.dataset.themePreference==='light');
  await themeButtons.filter({hasText:'Oscuro'}).click();
  await page.waitForFunction(()=>document.documentElement.dataset.themePreference==='dark'&&document.documentElement.dataset.theme==='dark');
  const darkCardColor=await page.locator('.dashboard-prime-card').first().evaluate(node=>getComputedStyle(node).backgroundColor);
  if(darkCardColor!=='rgb(30, 41, 59)')throw Error(`La tarjeta PrimeReact no adoptó el fondo oscuro: ${darkCardColor}`);
  const darkMetricColor=await page.locator('.delay-metric-strip > div').first().evaluate(node=>getComputedStyle(node).backgroundColor);
  if(darkMetricColor!=='rgb(23, 32, 51)')throw Error(`La métrica interna no adoptó el fondo oscuro: ${darkMetricColor}`);
  const darkFilterColor=await page.locator('.operational-alert-panel .row-action').first().evaluate(node=>getComputedStyle(node).color);
  if(darkFilterColor!=='rgb(226, 232, 240)')throw Error(`El filtro de alertas perdió contraste en modo oscuro: ${darkFilterColor}`);
  if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'resumen-oscuro.png'),fullPage:true});
  await themeButtons.filter({hasText:'Sistema'}).click();
  await page.waitForFunction(()=>document.documentElement.dataset.themePreference==='system');
  const priorityBoxes=await page.locator('.dashboard-priority').evaluateAll(nodes=>nodes.map(node=>{const box=node.getBoundingClientRect();return {top:box.top,bottom:box.bottom}}));
  for(let index=1;index<priorityBoxes.length;index++)if(priorityBoxes[index].top<priorityBoxes[index-1].bottom)throw Error(`Las prioridades se solapan: ${JSON.stringify(priorityBoxes)}`);
  await page.evaluate(()=>setSidebarCollapsed(true));
  await page.waitForTimeout(320);
  const collapsedChevron=await page.locator('#supervision-toggle').evaluate(node=>getComputedStyle(node,'::after').display);
  if(collapsedChevron!=='none')throw Error('El chevron sigue visible con el menú minimizado');
  const collapsedLayout=await page.evaluate(()=>({viewport:innerWidth,sidebar:Math.round(document.querySelector('aside').getBoundingClientRect().width)}));
  if(collapsedLayout.viewport>900&&collapsedLayout.sidebar!==72)throw Error(`El sidebar minimizado no conserva 72 px: ${JSON.stringify(collapsedLayout)}`);
  if(screenshotDir)await page.locator('aside').screenshot({path:path.join(screenshotDir,'resumen-sidebar-minimizado.png')});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>syncViewportClass());await page.waitForTimeout(250);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  if(overflow)throw Error(`Resumen desborda el ancho móvil: ${await page.evaluate(()=>document.documentElement.scrollWidth)} px`);
  if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'resumen-movil.png'),fullPage:true});
  await page.locator('#mobile-nav-toggle').click();await page.waitForTimeout(220);
  const mobileSupervision=await page.locator('#supervision-toggle').evaluate(node=>({text:getComputedStyle(node.querySelector('span')).display,chevron:getComputedStyle(node,'::after').display}));
  if(mobileSupervision.text==='none'||mobileSupervision.chevron==='none')throw Error(`Supervisión no se recupera al abrir el menú móvil: ${JSON.stringify(mobileSupervision)}`);
  await page.locator('#sidebar-backdrop').click({position:{x:380,y:100}});
  await page.setViewportSize({width:1100,height:820});await page.evaluate(()=>{setSidebarCollapsed(false);syncViewportClass()});await page.waitForTimeout(250);
  await page.evaluate(async()=>{state.page='standards';await render()});
  const arrivalOverflow=await page.evaluate(()=>({document:document.documentElement.scrollWidth>innerWidth,items:[...document.querySelectorAll('.arrival-details,.coverage-summary,.arrival-service,.arrival-zone')].filter(node=>node.scrollWidth>node.clientWidth+1).map(node=>({className:node.className,client:node.clientWidth,scroll:node.scrollWidth}))}));
  if(arrivalOverflow.document||arrivalOverflow.items.length)throw Error(`Tiempos de arribo desborda contenedores: ${JSON.stringify(arrivalOverflow)}`);
  const clippedActions=await page.locator('.standard-actions button').evaluateAll(buttons=>buttons.filter(button=>{const buttonBox=button.getBoundingClientRect(),panelBox=button.closest('.arrival-details').getBoundingClientRect();return buttonBox.left<panelBox.left-1||buttonBox.right>panelBox.right+1}).map(button=>button.textContent));
  if(clippedActions.length)throw Error(`Acciones de arribo recortadas: ${clippedActions.join('|')}`);
  if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'arribos-escritorio.png'),fullPage:true});
  await page.setViewportSize({width:375,height:812});await page.evaluate(()=>syncViewportClass());await page.waitForTimeout(250);
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Tiempos de arribo desborda el ancho móvil');
  if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'arribos-movil.png'),fullPage:true});
  if(errors.length)throw Error(errors.join('\n'));
  console.log('UI Resumen y Tiempos de arribo: PrimeReact, temas, jerarquía y ausencia de desbordamientos verificados con datos sintéticos.');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
