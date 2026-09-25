const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');

const projectRoot=path.resolve(__dirname,'../..');
const screenshotDir=process.env.UX_SCREENSHOT_DIR?path.resolve(process.env.UX_SCREENSHOT_DIR):null;
if(screenshotDir)fs.mkdirSync(screenshotDir,{recursive:true});

const notices=[
 {id:11,task_number:'AV-1001',phone:'099 111 222',notice_type:'Volverán a llamar',audience:'TODOS',detail:'Cliente solicita contacto luego de las 16:00.',communicated_by:'Telefonista QA',managed_by:null,status:'PENDIENTE',comments:null,created_at:'2026-09-23T14:00:00-03:00'},
 {id:12,task_number:'AV-1002',phone:'098 333 444',notice_type:'Reclama no cumplimiento',audience:'PLANIFICADORES',detail:'Revisar coordinación informada y devolver respuesta.',communicated_by:'Telefonista QA',managed_by:'Supervisor QA',status:'EN_GESTION',comments:'Prestador consultado.',created_at:'2026-09-23T13:10:00-03:00'}
];

(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],messages=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>messages.push(`${message.type()}: ${message.text()}`));
  let html=fs.readFileSync(path.join(projectRoot,'app/static/index.html'),'utf8');
  html=html.replace(/<link\b[^>]*>/gi,'').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
  await page.route('http://notices.test/',route=>route.fulfill({status:200,contentType:'text/html',body:html}));
  await page.route('http://notices.test/static/frontend/**',route=>{
   const relative=decodeURIComponent(new URL(route.request().url()).pathname.replace('/static/frontend/',''));
   const file=path.join(projectRoot,'app/static/frontend',relative);
   const contentType=file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'application/octet-stream';
   route.fulfill({status:200,contentType,body:fs.readFileSync(file)});
  });
  await page.goto('http://notices.test/');
  for(const file of ['styles.css','settings.css','operations.css','dashboard.css','quotes.css','auth.css'])await page.addStyleTag({path:path.join(projectRoot,'app/static',file)});
  await page.addStyleTag({url:'http://notices.test/static/frontend/prime-react.css'});
  await page.evaluate(()=>{window.libroTrabajoUIReady=import('/static/frontend/prime-react.js')});
  await page.waitForFunction(()=>Boolean(window.LibroTrabajoUI));
  await page.addScriptTag({content:`window.fetch=async input=>{const url=String(input);if(url==='/api/auth/me')return new Promise(()=>{});let payload;if(url.startsWith('/api/notices?'))payload=${JSON.stringify(notices)};else if(url==='/api/notices/assignees')payload=[{display_name:'Supervisor QA',role_name:'Supervisor'},{display_name:'Telefonista QA',role_name:'Telefonista'}];else if(url.endsWith('/history'))payload=[];else throw Error('Petición sintética no prevista: '+url);return {ok:true,status:200,text:async()=>JSON.stringify(payload)}};`});
  await page.addScriptTag({path:path.join(projectRoot,'app/static/app.js')});
  await page.evaluate(async()=>{authUser={id:7,display_name:'Supervisor QA',role_name:'Supervisor',permissions:['notices.view','notices.create','notices.assign','notices.comment','notices.change_status','notices.close']};currentUser=authUser.display_name;state.page='notices';await render()});

  if(await page.locator('#content').getAttribute('data-renderer')!=='prime-react-notices'){
   const diagnostics=await page.evaluate(async()=>({ready:Boolean(window.libroTrabajoUIReady),bridge:Object.keys(window.LibroTrabajoUI||{}),module:Object.keys(await window.libroTrabajoUIReady),content:document.querySelector('#content')?.innerHTML.slice(0,300)}));
   throw Error(`Avisos no quedó montado con PrimeReact: ${JSON.stringify(diagnostics)} · ${messages.join(' | ')} · ${errors.join(' | ')}`);
  }
  if(await page.locator('.notice-prime-metric.p-card').count()!==4)throw Error('Las métricas de Avisos no usan cuatro tarjetas PrimeReact');
  if(await page.locator('.notice-prime-table.p-datatable').count()!==1)throw Error('La tabla de Avisos no usa DataTable de PrimeReact');
  if(await page.locator('.health').count())throw Error('El Header todavía muestra Sistema activo');
  if(await page.locator('#subtitle').count())throw Error('El Header todavía conserva el subtítulo global');
  const themeLabels=await page.locator('#theme-toggle-root .p-button').allTextContents();
  if(themeLabels.join('|')!=='Sistema|Claro|Oscuro')throw Error(`Selector de tema incompleto: ${themeLabels.join('|')}`);
  await page.locator('#profile-button').click();
  if(!await page.locator('#profile-popover').isVisible())throw Error('El perfil no despliega su panel');
  await page.keyboard.press('Escape');
  const logoutColor=await page.locator('#user-button').evaluate(node=>getComputedStyle(node).color);
  if(logoutColor!=='rgb(220, 38, 38)')throw Error(`Salir no usa rojo semántico: ${logoutColor}`);

  const headings=await page.locator('.notice-table thead th').allTextContents();
  if(headings.includes('Acciones')||!headings.includes('Opciones'))throw Error(`Encabezados incorrectos: ${headings.join('|')}`);
  if(await page.getByText('Gestionar',{exact:true}).count())throw Error('La tabla todavía muestra Gestionar');
  const headerHeight=await page.locator('.notice-table thead tr').evaluate(node=>Math.round(node.getBoundingClientRect().height));
  if(headerHeight<36||headerHeight>40)throw Error(`El encabezado de DataTable no es compacto: ${headerHeight}px`);
  const rowHeights=await page.locator('.notice-table tbody tr').evaluateAll(rows=>rows.map(row=>Math.round(row.getBoundingClientRect().height)));
  if(rowHeights.some(height=>height<36||height>40))throw Error(`Las filas de DataTable no mantienen 36–40 px: ${rowHeights.join('|')}`);
  await page.locator('#theme-toggle-root .p-button').filter({hasText:'Oscuro'}).click();
  await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
  await page.waitForTimeout(250);
  const darkCellColor=await page.locator('.notice-table tbody td').first().evaluate(node=>getComputedStyle(node).backgroundColor);
  if(darkCellColor!=='rgb(30, 41, 59)')throw Error(`DataTable no adoptó el tema oscuro: ${darkCellColor}`);
  const darkHeaderColors=await page.evaluate(()=>({theme:getComputedStyle(document.querySelector('#theme-toggle-root .p-button')).backgroundColor,profile:getComputedStyle(document.querySelector('#profile-button')).backgroundColor,logout:getComputedStyle(document.querySelector('#user-button')).backgroundColor}));
  if(darkHeaderColors.theme!=='rgb(30, 41, 59)'||darkHeaderColors.profile!=='rgb(30, 41, 59)'||darkHeaderColors.logout!=='rgb(69, 10, 10)')throw Error(`El Header no adoptó superficies oscuras: ${JSON.stringify(darkHeaderColors)}`);
  if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'avisos-tabla-oscuro.png'),fullPage:true});
  await page.locator('#theme-toggle-root .p-button').filter({hasText:'Sistema'}).click();
  await page.waitForFunction(()=>document.documentElement.dataset.themePreference==='system');
  const unassigned=page.locator('.notice-table tbody tr').filter({hasText:'AV-1001'});
  if(!await unassigned.getByText('Asignarme este caso',{exact:true}).count())throw Error('Falta la autoasignación dentro de Responsable');
  const supervisorMenu=unassigned.locator('.notice-actions-menu');await supervisorMenu.locator('summary').click();
  const supervisorActions=await supervisorMenu.locator('[role="menuitem"]').allTextContents();
  if(supervisorActions.join('|')!=='Asignar|Editar|Historial')throw Error(`Menú de Supervisor incorrecto: ${supervisorActions.join('|')}`);
  await page.keyboard.press('Escape');

  const status=unassigned.locator('.status-dropdown');await status.locator('summary').click();
  const geometry=await status.evaluate(node=>{const trigger=node.querySelector('summary').getBoundingClientRect(),menu=node.querySelector('.status-options').getBoundingClientRect();return {triggerBottom:trigger.bottom,menuTop:menu.top,visible:getComputedStyle(node.querySelector('.status-options')).visibility}});
  if(geometry.menuTop<geometry.triggerBottom+4)throw Error(`El menú de estado no abre debajo: ${JSON.stringify(geometry)}`);
  await page.keyboard.press('Escape');

  await page.evaluate(()=>openForm('notice'));
  const modal=page.locator('#modal');
  const labels=await modal.locator('#fields label').allTextContents();
  if(!labels.includes('Número de tarea (opcional)')||!labels.includes('Teléfono del cliente (opcional)'))throw Error(`Etiquetas opcionales incorrectas: ${labels.join('|')}`);
  const motives=await modal.locator('select[name="notice_type"] option').allTextContents();
  for(const expected of ['Volverán a llamar','Reclama no cumplimiento','Se envió HSM'])if(!motives.includes(expected))throw Error(`Falta el motivo ${expected}`);
  if((await modal.innerText()).includes('La fecha, hora y usuario'))throw Error('El modal conserva ayuda técnica');
  if(screenshotDir)await modal.screenshot({path:path.join(screenshotDir,'avisos-nuevo-modal.png')});
  await modal.evaluate(dialog=>dialog.close());
  await page.locator('.notice-prime-table .p-datatable-wrapper').evaluate(node=>node.scrollLeft=0);
  if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'avisos-tabla-escritorio.png'),fullPage:true});

  await page.evaluate(async()=>{authUser={id:8,display_name:'Consulta QA',role_name:'Telefonista',permissions:['notices.view']};currentUser=authUser.display_name;await render()});
  const restrictedMenu=page.locator('.notice-table tbody tr').first().locator('.notice-actions-menu');await restrictedMenu.locator('summary').click();
  const restrictedActions=await restrictedMenu.locator('[role="menuitem"]').allTextContents();
  if(restrictedActions.join('|')!=='Historial')throw Error(`Menú restringido incorrecto: ${restrictedActions.join('|')}`);
  await page.keyboard.press('Escape');

  await page.setViewportSize({width:375,height:812});await page.evaluate(()=>syncViewportClass());await page.waitForTimeout(250);
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Avisos desborda el ancho móvil');
  await page.locator('.notice-table tbody tr').first().locator('.notice-actions-menu summary').click();
  const mobileMenu=page.locator('.notice-actions-menu[open] .notice-actions-pop'),mobileViewport=page.viewportSize();const box=await mobileMenu.boundingBox();
  if(!box||box.x<0||box.x+box.width>mobileViewport.width||box.y<0||box.y+box.height>mobileViewport.height)throw Error(`Menú contextual fuera del viewport móvil: ${JSON.stringify(box)}`);
  await page.locator('.skip-link').evaluate(element=>element.style.visibility='hidden');
  if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'avisos-tabla-movil.png'),fullPage:true});
  await page.keyboard.press('Escape');
  await page.setViewportSize({width:844,height:390});await page.evaluate(()=>syncViewportClass());await page.waitForTimeout(250);
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Avisos desborda el ancho móvil horizontal');
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.locator('.notice-table tbody tr').first().locator('.notice-actions-menu summary').click();
  if(!await page.locator('.notice-actions-menu[open] .notice-actions-pop').isVisible())throw Error('El menú contextual no funciona con movimiento reducido');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('UI Avisos: modal, autoasignación, permisos, menús y posicionamiento verificados con datos sintéticos.');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
