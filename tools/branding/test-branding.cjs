// Solo abre la página pública local con un perfil temporal, sin credenciales.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:860}});
  await page.route('**/*',r=>new URL(r.request().url()).origin==='http://127.0.0.1:8000'?r.continue():r.abort());
  await page.goto('http://127.0.0.1:8000/',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.title==='Libro de Trabajo · Centro Operativo'&&document.querySelector('.brand img')?.naturalWidth>0);
  await page.getByRole('heading',{name:'Ingresar a Libro de Trabajo'}).waitFor();
  if(!(await page.locator('link[rel=icon]').getAttribute('href')).endsWith('libro-trabajo.ico'))throw Error('Falta favicon');
  fs.mkdirSync(path.resolve('.build'),{recursive:true});
  await page.screenshot({path:path.resolve('.build/libro-trabajo-preview.png')});
  console.log('Identidad verificada: título, libro SVG, login y favicon. Sin iniciar sesión.');
 }finally{await browser.close()}
})().catch(()=>{console.error('Falló la comprobación visual local.');process.exitCode=1});
