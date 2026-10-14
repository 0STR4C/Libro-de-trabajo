import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { ProgressSpinner } from 'primereact/progressspinner';
import { DashboardView, SupervisionDashboardView } from './dashboard.jsx';
import { DelayAuditView } from './delay-audit.jsx';
import { NoticesView, DelaysView } from './operations.jsx';
import { QuoteView } from './quotes.jsx';
import { TransfersView } from './transfers.jsx';
import { SchedulesView } from './schedules.jsx';
import { ArrivalTimesView as StandardsView } from './arrival-times.jsx';
import { SettingsView } from './settings.jsx';
import { AuditView } from './audit.jsx';
import { WfmView } from './wfm.jsx';
import { LoginView, LogoutDialog } from './login.jsx';

const departments = ['ARTIGAS','CANELONES','CERRO LARGO','COLONIA','DURAZNO','FLORES','FLORIDA','LAVALLEJA','MALDONADO','MONTEVIDEO','PAYSANDÚ','RÍO NEGRO','RIVERA','ROCHA','SALTO','SAN JOSÉ','SORIANO','TACUAREMBÓ','TREINTA Y TRES'];
const services = ['GRÚA','ML','SINIESTROS'];
const names = { dashboard:'Resumen operativo', notices:'Avisos del equipo', quotes:'Cotizador de servicios', delays:'Zonas con demora', transfers:'Programados', schedules:'Horarios del equipo', standards:'Tiempos de arribo', supervision:'Dashboard de Supervisión', delayAudit:'Auditoría de demoras', wfm:'Planificación de horarios', audit:'Registro de auditoría', settings:'Configuración' };
const permission = { dashboard:'dashboard.view', notices:'notices.view', quotes:'quotes.view', delays:'delays.view', transfers:'transfers.view', schedules:'schedules.view', standards:'standards.view', supervision:'dashboard.view', delayAudit:'delays.view', wfm:'schedules.view', audit:'audit.view', settings:'settings.manage' };
const components = { dashboard:DashboardView, notices:NoticesView, quotes:QuoteView, delays:DelaysView, transfers:TransfersView, schedules:SchedulesView, standards:StandardsView, supervision:SupervisionDashboardView, delayAudit:DelayAuditView, wfm:WfmView, audit:AuditView, settings:SettingsView };
const memoizedComponents = Object.fromEntries(Object.entries(components).map(([key,View])=>[key,React.memo(View)]));
const statusLabel = value => ({ SIN_ASIGNAR:'Sin asignar', ASIGNADO:'Asignado', EN_CURSO:'En curso', FINALIZADO:'Finalizado', CANCELADO:'Cancelado', PENDIENTE:'Sin asignar', CONFIRMADO:'Asignado', COMPLETADO:'Finalizado' }[value] || String(value || '').replaceAll('_',' '));
const iso = value => `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}`;
const monday = (value = new Date()) => { const day = value instanceof Date ? new Date(value) : new Date(`${value}T12:00:00`); day.setDate(day.getDate() - (day.getDay()+6)%7); return iso(day); };
const shift = (value, days) => { const day = new Date(`${value}T12:00:00`); day.setDate(day.getDate()+days); return iso(day); };
const query = entries => { const params = new URLSearchParams(); Object.entries(entries).forEach(([key,value]) => { if (value !== '' && value != null) params.set(key,value); }); return params; };
const options = (values, all) => [{label:all,value:''},...values.map(value=>({label:value,value}))];
const initialFilters = () => ({
  notices:{view:'open',from:'',to:'',status:'',task:'',contact:'',search:'',limit:50},
  delays:{view:'active',from:'',to:'',department:'',service:'',search:'',limit:50},
  delayAudit:{scope:'all',from:'',to:'',department:'',search:'',limit:50},
  transfers:{view:'active',from:'',to:'',status:'',type:'',task:'',provider:'',responsible:'',search:''},
  schedules:{view:'history',week:monday(),from:'',to:'',employee:'team',role:'',search:''},
  standards:{department:'',service:'',status:'all'},
  audit:{from:'',to:'',entity:'',entityId:'',action:'',actorId:'',search:'',limit:50},
  settings:{tab:'roles'}, wfm:{day:iso(new Date()),team:'Telefonista'}
});

function errorText(value, fallback='No se pudo completar la operación') {
  if (typeof value === 'string' && value.trim()) return value;
  if (Array.isArray(value)) return value.map(item => errorText(item,'')).filter(Boolean).join(' · ') || fallback;
  if (value && typeof value === 'object') return errorText(value.detail ?? value.message ?? value.msg, fallback);
  return fallback;
}
const cookie = name => document.cookie.split(';').map(value=>value.trim()).find(value=>value.startsWith(`${name}=`))?.slice(name.length+1)||'';
async function request(url, options={}) {
  const method=(options.method||'GET').toUpperCase();
  const token = ['POST','PUT','PATCH','DELETE'].includes(method) ? cookie('centro_csrf') : '';
  const response=await fetch(url,{credentials:'same-origin',...options,headers:{'Content-Type':'application/json',...(token?{'X-CSRF-Token':decodeURIComponent(token)}:{}),...options.headers}});
  const raw=await response.text();
  let payload=null; if(raw) try { payload=JSON.parse(raw); } catch { /* Error handled below. */ }
  if(response.status===401 && !['/api/auth/me','/api/auth/login'].includes(url))window.dispatchEvent(new Event('libro:unauthorized'));
  if(!response.ok){const failure=new Error(errorText(payload?.detail,`Error de operación (${response.status})`));failure.status=response.status;throw failure;}
  if(raw && payload===null) throw new Error('El servidor respondió con un formato inesperado');
  return payload;
}

async function download(kind, filters, notify) {
  try {
    const response=await fetch(`/api/reports/${kind}.csv?${filters}`,{credentials:'same-origin'});
    if(!response.ok) throw new Error(errorText((await response.json()).detail,'No se pudo descargar el reporte'));
    const link=document.createElement('a'),url=URL.createObjectURL(await response.blob());
    link.href=url;link.download=`reporte_${kind}_${iso(new Date())}.csv`;document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);notify('Reporte descargado');
  } catch(error){notify(error.message,'error');}
}

function pageQuery(page, filter) {
  if(page==='notices') return query({date_from:filter.from,date_to:filter.to,status:filter.status,task:filter.task,contact:filter.contact,q:filter.search,scope:filter.view,limit:filter.limit||50});
  if(page==='delays') return query({date_from:filter.from,date_to:filter.to,scope:filter.view==='active'?'current':filter.view==='review'?'review':filter.view==='history'?'normalized':'',department:filter.department,service:filter.service,q:filter.search,limit:filter.limit||50});
  if(page==='delayAudit') return query({date_from:filter.from,date_to:filter.to,scope:filter.scope,department:filter.department,q:filter.search,limit:filter.limit||50});
  if(page==='transfers') return query({date_from:filter.from,date_to:filter.to,status:filter.status||(filter.view==='active'?'ACTIVE':filter.view==='finished'?'FINALIZADO':filter.view==='cancelled'?'CANCELADO':''),transfer_type:filter.type,task:filter.task,provider:filter.provider,responsible:filter.responsible,q:filter.search});
  if(page==='audit') return query({date_from:filter.from,date_to:filter.to,entity:filter.entity,entity_id:filter.entityId,action:filter.action,actor_id:filter.actorId,q:filter.search,limit:filter.limit||50});
  if(page==='schedules') return query({...(filter.view==='week'?{week:filter.week}:{date_from:filter.from,date_to:filter.to}),employee_id:filter.employee==='mine'?filter.userId:filter.employee==='team'?'':filter.employee,role:filter.role,q:filter.search});
  return new URLSearchParams();
}

async function loadModel(page, filters, actor, actions) {
  const can = action => actor.permissions?.includes(action);
  const currentUser=actor.display_name;
  const common={request:request,refresh:()=>actions.refresh(page),currentUser};
  const f=filters[page];
  const parameters=pageQuery(page,f);
  const update=(next, target=page)=>{filters[target]={...filters[target],...next};return actions.refresh(target);};
  const report=(kind=page, params=parameters)=>download(kind,params,actions.notify);
  if(page==='notices'){
    const result=await request(`/api/notices/page?${query({...Object.fromEntries(parameters),offset:0})}`);
    return {...common,page:result,activeView:f.view,viewOptions:[{label:'Activos',value:'open'},{label:'Sin responsable',value:'unassigned'},{label:'Asignados a mí',value:'mine'},{label:'Esperando respuesta',value:'waiting'},{label:'Resueltos',value:'resolved'},{label:'Todos / históricos',value:'all'}],statusOptions:[{label:'Todos los estados',value:''},{label:'Pendiente',value:'PENDIENTE'},{label:'En gestión',value:'EN_GESTION'},{label:'Esperando respuesta',value:'ESPERANDO_RESPUESTA'},{label:'Resuelto',value:'RESUELTO'},{label:'Cancelado',value:'CANCELADO'}],filters:f,metrics:[{value:'open',label:'Activos',help:'Requieren seguimiento',tone:'normal'},{value:'unassigned',label:'Sin responsable',help:'Nadie los tomó todavía',tone:'urgent'},{value:'mine',label:'Asignados a mí',help:'Tu cola de trabajo',tone:'mine'},{value:'waiting',label:'En espera',help:'Esperan una respuesta',tone:'waiting'}],age:row=>{const minutes=Math.max(0,Math.floor((Date.now()-new Date(row.created_at).getTime())/60000));return !Number.isFinite(minutes)?'—':minutes<60?`${Math.max(1,minutes)} min`:minutes<1440?`${Math.floor(minutes/60)} h`:`${Math.floor(minutes/1440)} d`;},canExport:can('reports.export'),canCreate:can('notices.create'),canAssign:can('notices.assign'),canComment:can('notices.comment'),canChangeStatus:can('notices.change_status'),canClose:can('notices.close'),onExport:()=>report('notices',pageQuery('notices',filters.notices)),onStateChange:(values,view,limit)=>{filters.notices={...values,view,limit:limit||filters.notices.limit||50};}};
  }
  if(page==='dashboard'||page==='supervision'){
    if(page==='supervision')return {dashboard:await request('/api/dashboard'),statusLabel};
    const [dashboard,geo,activeDelays,alerts]=await Promise.all([request('/api/dashboard'),fetch('/uruguay-departamentos.geojson').then(r=>r.json()),can('delays.view')?request('/api/delays?scope=current'):Promise.resolve([]),can('delays.view')&&can('standards.view')?request('/api/operational-alerts').catch(()=>[]):Promise.resolve([])]);
    return {dashboard,geo,activeDelays:activeDelays.filter(row=>row.is_current),alerts,showAlerts:can('delays.view')&&can('standards.view'),currentUser,statusLabel};
  }
  if(page==='quotes') return {...common,draftKey:`centroQuoteDraft:${actor.id||currentUser}`,canCreate:can('quotes.create'),canExport:can('reports.export'),onExport:values=>report('quotes',query({q:values.search,coverage:values.coverage,mode:values.mode}))};
  if(page==='delays'){
    const pageData=await request(`/api/delays/page?${parameters}`);
    return {...common,page:pageData,onPage:(offset,limit=filters.delays.limit||50)=>{filters.delays.limit=limit;return request(`/api/delays/page?${query({...Object.fromEntries(pageQuery('delays',filters.delays)),offset})}`);},filters:f,viewOptions:[{label:'Vigentes verificadas',value:'active'},{label:'Requieren revisión',value:'review'},{label:'Normalizadas / histórico',value:'history'},{label:'Todas',value:'all'}],departmentOptions:options(departments,'Todos los departamentos'),serviceOptions:options(services,'Todas las prestaciones'),canExport:can('reports.export'),canCreate:can('delays.create'),canNormalize:can('delays.normalize'),onApply:values=>update(values),onClear:()=>update({view:'active',from:'',to:'',department:'',service:'',search:''}),onExport:()=>report('delays')};
  }
  if(page==='delayAudit'){
    const pageData=await request(`/api/delays/page?${parameters}`);
    return {...common,page:pageData,filters:f,departments:options(departments,'Todos los departamentos'),onPage:(offset,limit=filters.delayAudit.limit||50)=>{filters.delayAudit.limit=limit;return request(`/api/delays/page?${query({...Object.fromEntries(pageQuery('delayAudit',filters.delayAudit)),offset})}`);},onApply:values=>update(values),onClear:()=>update({scope:'all',from:'',to:'',department:'',search:''})};
  }
  if(page==='transfers'){
    const rows=await request(`/api/transfers?${parameters}`);
    return {...common,rows,filters:f,viewOptions:[{label:'Pendientes',value:'active'},{label:'Finalizados',value:'finished'},{label:'Cancelados',value:'cancelled'},{label:'Todos',value:'all'}],statusOptions:options(['SIN_ASIGNAR','ASIGNADO','EN_CURSO','FINALIZADO','CANCELADO'],'Todos los estados').map(item=>({...item,label:item.value?statusLabel(item.value):item.label})),canExport:can('reports.export'),canCreate:can('transfers.create'),canManage:can('transfers.manage'),onApply:values=>update(values),onClear:()=>update({view:'active',from:'',to:'',status:'',type:'',task:'',provider:'',responsible:'',search:''}),onExport:()=>report('transfers')};
  }
  if(page==='schedules'){
    const manager=['Supervisor','Administrador'].includes(actor.role_name);
    const [people,rows,requests]=await Promise.all([manager?request('/api/schedules/people'):Promise.resolve([{id:actor.id,display_name:currentUser,role_name:actor.role_name}]),request(`/api/schedules?${pageQuery(page,{...f,userId:actor.id})}`),['Telefonista','Planificador','Supervisor'].includes(actor.role_name)?request('/api/wfm/requests?scope=mine'):Promise.resolve([])]);
    return {...common,people,rows,requests,manager,canRequest:['Telefonista','Planificador','Supervisor'].includes(actor.role_name),userId:actor.id,currentRole:actor.role_name,currentWeek:monday(),filters:f,onApply:values=>update(values),onStateChange:values=>{filters.schedules={...filters.schedules,...values};},canExport:manager&&can('reports.export'),onExport:params=>report('schedules',params)};
  }
  if(page==='standards'){
    const arrivalQuery=offset=>query({department:f.department,service:f.service,is_active:f.status==='active'?true:f.status==='inactive'?false:null,limit:50,offset});
    const [pageData,geography]=await Promise.all([request(`/api/arrival-times?${arrivalQuery(0)}`),request('/api/arrival-times/geography')]);
    return {...common,page:pageData,geography,filters:f,canManage:can('arrival_times.manage'),onPage:offset=>request(`/api/arrival-times?${arrivalQuery(offset)}`),onApply:values=>update(values),onClear:()=>update({department:'',service:'',status:'all'})};
  }
  if(page==='settings'){
    const [users,roles,permissions,wfmSettings,google,quoteRules,tolls,version]=await Promise.all([f.tab==='users'?request('/api/settings/users'):null,['users','roles'].includes(f.tab)?request('/api/settings/roles'):Promise.resolve([]),f.tab==='roles'?request('/api/settings/permissions'):Promise.resolve([]),f.tab==='general'&&actor.role_name==='Administrador'?request('/api/wfm/settings'):null,f.tab==='google'?request('/api/settings/google-access'):null,f.tab==='quotes'?request('/api/settings/quote-rules'):null,f.tab==='catalogs'?request('/api/settings/tolls'):null,f.tab==='news'?request('/api/settings/version'):null]);
    return {...common,users,roles,permissions,tab:f.tab,wfmSettings,google,quoteRules,tolls,version,onTab:value=>update({tab:value}),onWfm:()=>actions.navigate('wfm')};
  }
  if(page==='audit'){
    const pageData=await request(`/api/audit/page?${parameters}`);
    return {...common,page:pageData,onPage:(offset,limit=filters.audit.limit||50)=>{filters.audit.limit=limit;return request(`/api/audit/page?${query({...Object.fromEntries(pageQuery('audit',filters.audit)),offset})}`);},filters:f,onApply:values=>update(values),onClear:()=>update({from:'',to:'',entity:'',entityId:'',action:'',actorId:'',search:''}),canExport:can('reports.export'),onExport:()=>report('audit')};
  }
  if(page==='wfm'){
    if(!['Supervisor','Administrador'].includes(actor.role_name))throw new Error('Planificación reservada a supervisores');
    const [plan,requests]=await Promise.all([request(`/api/wfm/plan?date=${f.day}&team=${encodeURIComponent(f.team)}`),request(`/api/wfm/requests?team=${encodeURIComponent(f.team)}`).catch(()=>[])]);
    return {...common,day:f.day,team:f.team,plan,requests};
  }
  throw new Error('Pantalla no disponible');
}

const navMain=['dashboard','notices','quotes','delays','transfers','schedules','standards'];
const icons={dashboard:'pi-home',notices:'pi-bell',quotes:'pi-calculator',delays:'pi-map-marker',transfers:'pi-send',schedules:'pi-calendar',standards:'pi-clock',supervision:'pi-chart-bar',delayAudit:'pi-history',wfm:'pi-users',audit:'pi-list',settings:'pi-cog'};
const themeKey='libro-de-trabajo-theme';
function applyTheme(value){const selected=['light','dark','system'].includes(value)?value:'system',dark=selected==='system'?window.matchMedia('(prefers-color-scheme: dark)').matches:selected==='dark';document.documentElement.dataset.themePreference=selected;document.documentElement.dataset.theme=dark?'dark':'light';document.documentElement.classList.toggle('dark',dark);document.documentElement.classList.toggle('tw-dark',dark);document.documentElement.style.colorScheme=dark?'dark':'light';}

export function AppShell(){
  const [actor,setActor]=useState(null),[booting,setBooting]=useState(true),[page,setPage]=useState('dashboard'),[models,setModels]=useState({}),[loading,setLoading]=useState({}),[errors,setErrors]=useState({}),[profile,setProfile]=useState(false),[logout,setLogout]=useState(false),[supervision,setSupervision]=useState(false),[collapsed,setCollapsed]=useState(()=>localStorage.getItem('sidebarCollapsed')==='true'),[mobile,setMobile]=useState(false),[theme,setTheme]=useState(()=>localStorage.getItem(themeKey)||'system'),[message,setMessage]=useState(null);
  const filters=useRef(initialFilters()),actorRef=useRef(null),pageRef=useRef('dashboard'),sequence=useRef({}),notificationTimer=useRef(null);
  const notify=useCallback((value,kind='success')=>{setMessage({value,kind});clearTimeout(notificationTimer.current);notificationTimer.current=setTimeout(()=>setMessage(null),kind==='error'?5500:3200);},[]);
  const navigate=useCallback(next=>{pageRef.current=next;setPage(next);setMobile(false);setProfile(false);if(['supervision','delayAudit','audit','wfm'].includes(next))setSupervision(true);},[]);
  const refresh=useCallback(async(target=pageRef.current)=>{
    const user=actorRef.current;if(!user)return;
    const index=(sequence.current[target]||0)+1;sequence.current[target]=index;
    setLoading(current=>({...current,[target]:true}));setErrors(current=>({...current,[target]:null}));
    try{const model=await loadModel(target,filters.current,user,{refresh,navigate,notify});if(sequence.current[target]===index)setModels(current=>({...current,[target]:model}));return true;}
    catch(error){if(error.status===401){actorRef.current=null;setActor(null);setModels({});return false;}if(sequence.current[target]===index)setErrors(current=>({...current,[target]:error.message}));return false;}
    finally{if(sequence.current[target]===index)setLoading(current=>({...current,[target]:false}));}
  },[navigate,notify]);
  useEffect(()=>{window.toast=notify;request('/api/auth/me').then(user=>{actorRef.current=user;setActor(user);}).catch(()=>{actorRef.current=null;setActor(null);}).finally(()=>setBooting(false));return()=>{delete window.toast;clearTimeout(notificationTimer.current);};},[notify]);
  useEffect(()=>{const expired=()=>{actorRef.current=null;setModels({});setActor(null);setLogout(false);};window.addEventListener('libro:unauthorized',expired);return()=>window.removeEventListener('libro:unauthorized',expired);},[]);
  useEffect(()=>{if(actor&&!models[page])refresh(page);},[actor,page,refresh]);
  useEffect(()=>{applyTheme(theme);try{localStorage.setItem(themeKey,theme);}catch{}const media=window.matchMedia('(prefers-color-scheme: dark)'),listener=()=>{if(theme==='system')applyTheme('system');};media.addEventListener?.('change',listener);return()=>media.removeEventListener?.('change',listener);},[theme]);
  useEffect(()=>{document.body.classList.toggle('sidebar-collapsed',collapsed);try{localStorage.setItem('sidebarCollapsed',String(collapsed));}catch{}},[collapsed]);
  useEffect(()=>{const viewport=window.matchMedia('(max-width: 900px)'),sync=()=>{document.body.classList.toggle('mobile-viewport',viewport.matches);if(!viewport.matches)setMobile(false);};sync();viewport.addEventListener?.('change',sync);return()=>viewport.removeEventListener?.('change',sync);},[]);
  useEffect(()=>{document.body.classList.toggle('mobile-nav-open',mobile);},[mobile]);
  useEffect(()=>{document.body.classList.toggle('auth-locked',!actor);},[actor]);
  useEffect(()=>{const close=event=>{if(event.key==='Escape'||event.type==='click'&&!(event.target instanceof Element&&event.target.closest('.profile-control')))setProfile(false);};document.addEventListener('click',close);document.addEventListener('keydown',close);return()=>{document.removeEventListener('click',close);document.removeEventListener('keydown',close);};},[]);
  const signIn=async credentials=>{await request('/api/auth/login',{method:'POST',body:JSON.stringify(credentials)});const user=await request('/api/auth/me');actorRef.current=user;filters.current=initialFilters();setModels({});navigate('dashboard');setActor(user);};
  const signOut=async()=>{await request('/api/auth/logout',{method:'POST',body:'{}'});actorRef.current=null;filters.current=initialFilters();setModels({});setLogout(false);setActor(null);};
  const can=target=>Boolean(actor?.permissions?.includes(permission[target]))&&(!['supervision','delayAudit','wfm'].includes(target)||['Supervisor','Administrador'].includes(actor?.role_name));
  const visibleSupervision=['supervision','delayAudit','wfm','audit'].some(can);
  const navButton=target=><button key={target} type="button" data-page={target} className={`${target==='settings'?'settings-button ':''}${page===target?'active':''}`} aria-current={page===target?'page':undefined} onClick={()=>navigate(target)}><i className={`pi ${icons[target]}`} aria-hidden="true"/><span>{target==='dashboard'?'Resumen':target==='delays'?'Zonas con demora':target==='schedules'?'Horarios':target==='standards'?'Tiempos de arribo':target==='supervision'?'Dashboard':target==='delayAudit'?'Auditoría de demoras':target==='wfm'?'Planificación de horarios':target==='audit'?'Auditoría general':target==='settings'?'Configuración':target==='notices'?'Avisos':target==='quotes'?'Cotizador':'Programados'}</span></button>;
  if(booting)return <div className="page-loading" role="status">Comprobando sesión…</div>;
  if(!actor)return <LoginView model={{login:signIn}}/>;
  return <><a className="skip-link" href="#content">Saltar al contenido</a>{mobile&&<button className="sidebar-backdrop" aria-label="Cerrar navegación" onClick={()=>setMobile(false)}/>}
    <aside id="sidebar" aria-label="Navegación principal"><div className="sidebar-header"><div className="brand"><img src="/static/libro-trabajo.svg" alt="" width="46" height="46"/><div className="brand-text">Libro de<br/>Trabajo</div></div><button className="sidebar-toggle" type="button" aria-label={collapsed?'Expandir menú':'Contraer menú'} aria-expanded={!collapsed} onClick={()=>setCollapsed(value=>!value)}><i className="pi pi-angle-left"/></button></div><nav aria-label="Operación">{navMain.filter(can).map(navButton)}</nav><div className="sidebar-bottom">{visibleSupervision&&<div className="sidebar-supervision"><button className="sidebar-section-toggle" type="button" aria-expanded={supervision} onClick={()=>setSupervision(value=>!value)}><i className="pi pi-users"/><span>Supervisión</span></button>{supervision&&<div className="sidebar-submenu">{['supervision','delayAudit','wfm','audit'].filter(can).map(navButton)}</div>}</div>}{can('settings')&&navButton('settings')}</div></aside>
    <main id="prime-react-root"><header><div className="header-title"><button className="mobile-nav-toggle" type="button" aria-label="Abrir navegación" onClick={()=>setMobile(true)}>☰</button><div><h1>{names[page]}</h1></div></div><div className="header-actions"><div className="profile-control"><button className="user-button" type="button" aria-haspopup="dialog" aria-expanded={profile} onClick={()=>setProfile(value=>!value)}><i className="pi pi-user"/><span>{actor.display_name}</span><i className="pi pi-chevron-down profile-chevron"/></button>{profile&&<div className="profile-popover" role="dialog" aria-label="Perfil de usuario"><span>Sesión iniciada como</span><strong>{actor.display_name}</strong><small>{actor.role_name}</small><div className="profile-theme-row"><span>Apariencia</span><label className="theme-native-control"><i className="pi pi-palette"/><select aria-label="Cambiar tema visual" value={theme} onChange={event=>setTheme(event.target.value)}><option value="light">Claro</option><option value="dark">Oscuro</option><option value="system">Sistema</option></select></label></div></div>}</div><button className="logout-button tw-text-red-600 tw-bg-red-50 hover:tw-bg-red-100" type="button" onClick={()=>setLogout(true)}><i className="pi pi-sign-out"/><span>Salir</span></button></div></header>
      <section id="content" role="region" tabIndex="-1">{Object.keys(models).map(target=>{const View=memoizedComponents[target];return <div key={target} className={`operational-view tw-min-w-0 tw-w-full ${page!==target?'tw-hidden':''}`} hidden={page!==target} aria-hidden={page!==target}><View model={models[target]} active={page===target}/></div>;})}{loading[page]&&!models[page]&&<div className="page-loading tw-flex tw-items-center tw-gap-3" role="status"><ProgressSpinner style={{width:28,height:28}} strokeWidth="5"/>Cargando información…</div>}{errors[page]&&<div className="panel empty load-error" role="alert"><strong>No se pudo cargar esta pantalla</strong><p>{errors[page]}</p><Button label="Reintentar" onClick={()=>refresh(page)}/></div>}</section>
    </main>{logout&&<LogoutDialog model={{confirm:signOut,cancel:()=>setLogout(false)}}/>}{message&&<div id="toast" className={`show ${message.kind}`} role={message.kind==='error'?'alert':'status'}>{message.value}</div>}</>;
}
