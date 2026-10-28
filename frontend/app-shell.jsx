import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { ProgressSpinner } from 'primereact/progressspinner';
import { DashboardView, SupervisionDashboardView } from './dashboard.jsx';
import { DelayAuditView } from './delay-audit.jsx';
import { NoticesView, DelaysView } from './operations.jsx';
import { QuoteView } from './quotes.jsx';
import { TransfersView } from './transfers.jsx';
import { SchedulesView } from './schedules.jsx';
import { ScheduleRequestsView } from './schedule-requests.jsx';
import { SettingsView } from './settings.jsx';
import { AuditView } from './audit.jsx';
import { WfmView } from './wfm.jsx';
import { LoginView, LogoutDialog } from './login.jsx';
import { affectedViews } from './operational-invalidation.js';
import { requestDeadline, requestTimeoutError } from './request-deadline.js';
import { routes, routeFor, allowedRoute, firstAllowedRoute, parseRoute, routeUrl } from './routes.js';
import { displayLocation, displayService } from './operational-labels.js';

const departments = ['ARTIGAS','CANELONES','CERRO LARGO','COLONIA','DURAZNO','FLORES','FLORIDA','LAVALLEJA','MALDONADO','MONTEVIDEO','PAYSANDÚ','RÍO NEGRO','RIVERA','ROCHA','SALTO','SAN JOSÉ','SORIANO','TACUAREMBÓ','TREINTA Y TRES'];
const services = ['GRÚA','ML','SINIESTROS'];
const components = { dashboard:DashboardView, notices:NoticesView, quotes:QuoteView, delays:DelaysView, transfers:TransfersView, schedules:SchedulesView, requests:ScheduleRequestsView, supervision:SupervisionDashboardView, delayAudit:DelayAuditView, wfm:WfmView, audit:AuditView, settings:SettingsView };
const memoizedComponents = Object.fromEntries(Object.entries(components).map(([key,View])=>[key,React.memo(View)]));
const statusLabel = value => ({ SIN_ASIGNAR:'Sin asignar', ASIGNADO:'Asignado', EN_CURSO:'En curso', FINALIZADO:'Finalizado', CANCELADO:'Cancelado', PENDIENTE:'Sin asignar', CONFIRMADO:'Asignado', COMPLETADO:'Finalizado' }[value] || String(value || '').replaceAll('_',' '));
const iso = value => `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}`;
const monday = (value = new Date()) => { const day = value instanceof Date ? new Date(value) : new Date(`${value}T12:00:00`); day.setDate(day.getDate() - (day.getDay()+6)%7); return iso(day); };
const shift = (value, days) => { const day = new Date(`${value}T12:00:00`); day.setDate(day.getDate()+days); return iso(day); };
const query = entries => { const params = new URLSearchParams(); Object.entries(entries).forEach(([key,value]) => { if (value !== '' && value != null) params.set(key,value); }); return params; };
const options = (values, all, display = value => value) => [{label:all,value:''},...values.map(value=>({label:display(value),value}))];
const initialFilters = () => ({
  notices:{view:'open',from:'',to:'',status:'',task:'',contact:'',search:'',limit:50},
  quotes:{tab:'new'},
  delays:{view:'active',from:'',to:'',department:'',service:'',search:'',limit:50},
  delayAudit:{scope:'all',from:'',to:'',department:'',search:'',limit:50},
  transfers:{view:'active',from:'',to:'',status:'',type:'',task:'',provider:'',responsible:'',search:''},
  schedules:{view:'team',week:monday()},
  standards:{department:'',service:'',status:'all'},
  audit:{from:'',to:'',entity:'',entityId:'',action:'',actorId:'',search:'',limit:50},
  settings:{tab:'roles'}, wfm:{day:iso(new Date()),team:'Telefonista'}
});
function filtersFromLocation() {
  const filters = initialFilters();
  const parsed = parseRoute(window.location.pathname, window.location.search);
  if (parsed.route?.page === 'settings') {
    filters.settings.tab = parsed.route.tab;
    if (parsed.route.tab === 'arrival-times') Object.assign(filters.standards, parsed.filters);
  } else if (parsed.route && filters[parsed.route.page]) Object.assign(filters[parsed.route.page], parsed.filters);
  return { filters, parsed };
}
function currentRouteFilters(route, filters) {
  return route?.page === 'settings' && route.tab === 'arrival-times' ? filters.standards : filters[route?.page] || {};
}

function errorText(value, fallback='No se pudo completar la operación') {
  if (typeof value === 'string' && value.trim()) return value;
  if (Array.isArray(value)) return value.map(item => errorText(item,'')).filter(Boolean).join(' · ') || fallback;
  if (value && typeof value === 'object') return errorText(value.detail ?? value.message ?? value.msg, fallback);
  return fallback;
}
const cookie = name => document.cookie.split(';').map(value=>value.trim()).find(value=>value.startsWith(`${name}=`))?.slice(name.length+1)||'';
let sessionGeneration=0;
const pendingRequests=new Set();
function invalidateSessionRequests(){
  sessionGeneration+=1;
  for(const controller of pendingRequests)controller.abort();
  pendingRequests.clear();
}
async function sendRequest(url, options={}) {
  const generation=sessionGeneration,controller=new AbortController();
  pendingRequests.add(controller);
  const method=(options.method||'GET').toUpperCase();
  const changesData=['POST','PUT','PATCH','DELETE'].includes(method);
  const deadline=requestDeadline(controller);
  const token = ['POST','PUT','PATCH','DELETE'].includes(method) ? cookie('centro_csrf') : '';
  let response,raw;
  try{
    response=await fetch(url,{credentials:'same-origin',...options,signal:controller.signal,headers:{'Content-Type':'application/json',...(token?{'X-CSRF-Token':decodeURIComponent(token)}:{}),...options.headers}});
    raw=await response.text();
  }catch(error){
    if(generation!==sessionGeneration)throw Object.assign(new Error('La sesión cambió'),{stale:true});
    if(deadline.expired())throw requestTimeoutError(changesData);
    if(changesData)throw Object.assign(new Error('No se pudo confirmar si el cambio se guardó. Consultá el estado actual antes de volver a intentarlo.'),{uncertain:true,cause:error});
    throw error;
  }finally{deadline.clear();pendingRequests.delete(controller);}
  if(generation!==sessionGeneration)throw Object.assign(new Error('La sesión cambió'),{stale:true});
  let payload=null; if(raw) try { payload=JSON.parse(raw); } catch { /* Error handled below. */ }
  if(response.status===401 && !['/api/auth/me','/api/auth/login'].includes(url))window.dispatchEvent(new Event('libro:unauthorized'));
  if(!response.ok){const failure=new Error(errorText(payload?.detail,`Error de operación (${response.status})`));failure.status=response.status;failure.payload=payload;throw failure;}
  if(raw && payload===null) throw new Error('El servidor respondió con un formato inesperado');
  if(['POST','PUT','PATCH','DELETE'].includes(method) && /^\/api\/(?:notices|delays|transfers|arrival-times|schedules|wfm)(?:\/|$)/.test(url)) window.dispatchEvent(new CustomEvent('libro:operational-change',{detail:{url,method}}));
  return payload;
}

async function download(kind, filters, notify) {
  const generation=sessionGeneration;
  const controller=new AbortController(),deadline=requestDeadline(controller);
  pendingRequests.add(controller);
  try {
    const response=await fetch(`/api/reports/${kind}.csv?${filters}`,{credentials:'same-origin',signal:controller.signal});
    if(generation!==sessionGeneration)return;
    if(!response.ok) throw new Error(errorText((await response.json()).detail,'No se pudo descargar el reporte'));
    const blob=await response.blob();
    if(generation!==sessionGeneration)return;
    const link=document.createElement('a'),url=URL.createObjectURL(blob);
    link.href=url;link.download=`reporte_${kind}_${iso(new Date())}.csv`;document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);notify('Reporte descargado');
  } catch(error){if(generation===sessionGeneration)notify(deadline.expired()?requestTimeoutError(false).message:error.message,'error');}
  finally{deadline.clear();pendingRequests.delete(controller);}
}

function pageQuery(page, filter) {
  if(page==='notices') return query({date_from:filter.from,date_to:filter.to,status:filter.status,task:filter.task,contact:filter.contact,q:filter.search,scope:filter.view,limit:filter.limit||50});
  if(page==='delays') return query({date_from:filter.from,date_to:filter.to,scope:filter.view==='active'?'current':filter.view==='review'?'review':filter.view==='history'?'normalized':'',department:filter.department,service:filter.service,q:filter.search,limit:filter.limit||50});
  if(page==='delayAudit') return query({date_from:filter.from,date_to:filter.to,scope:filter.scope,department:filter.department,q:filter.search,limit:filter.limit||50});
  if(page==='transfers') return query({date_from:filter.from,date_to:filter.to,status:filter.status||(filter.view==='active'?'ACTIVE':filter.view==='finished'?'FINALIZADO':filter.view==='cancelled'?'CANCELADO':''),transfer_type:filter.type,task:filter.task,provider:filter.provider,responsible:filter.responsible,q:filter.search});
  if(page==='audit') return query({date_from:filter.from,date_to:filter.to,entity:filter.entity,entity_id:filter.entityId,action:filter.action,actor_id:filter.actorId,q:filter.search,limit:filter.limit||50});
  if(page==='schedules') return query({week:filter.week});
  return new URLSearchParams();
}

async function loadModel(page, filters, actor, actions) {
  const generation=sessionGeneration;
  const request=(url,options)=>generation===sessionGeneration?sendRequest(url,options):Promise.reject(Object.assign(new Error('La sesión cambió'),{stale:true}));
  const can = action => actor.permissions?.includes(action);
  const currentUser=actor.display_name;
  const common={request,refresh:()=>generation===sessionGeneration?actions.refresh(page):Promise.resolve(false),currentUser};
  const f=filters[page];
  const parameters=pageQuery(page,f);
  const update=(next, target=page)=>{if(generation!==sessionGeneration)return Promise.resolve(false);filters[target]={...filters[target],...next};actions.syncUrl(target);return actions.refresh(target);};
  const report=(kind=page, params=parameters)=>download(kind,params,actions.notify);
  if(page==='notices'){
    const result=await request(`/api/notices/page?${query({...Object.fromEntries(parameters),offset:0})}`);
    return {...common,page:result,activeView:f.view,viewOptions:[{label:'Activos',value:'open'},{label:'Sin responsable',value:'unassigned'},{label:'Asignados a mí',value:'mine'},{label:'Esperando respuesta',value:'waiting'},{label:'Resueltos',value:'resolved'},{label:'Todos / históricos',value:'all'}],statusOptions:[{label:'Todos los estados',value:''},{label:'Pendiente',value:'PENDIENTE'},{label:'En gestión',value:'EN_GESTION'},{label:'Esperando respuesta',value:'ESPERANDO_RESPUESTA'},{label:'Resuelto',value:'RESUELTO'},{label:'Cancelado',value:'CANCELADO'}],filters:f,metrics:[{value:'open',label:'Activos',help:'Requieren seguimiento',tone:'normal'},{value:'unassigned',label:'Sin responsable',help:'Nadie los tomó todavía',tone:'urgent'},{value:'mine',label:'Asignados a mí',help:'Tu cola de trabajo',tone:'mine'},{value:'waiting',label:'En espera',help:'Esperan una respuesta',tone:'waiting'}],age:row=>{const minutes=Math.max(0,Math.floor((Date.now()-new Date(row.created_at).getTime())/60000));return !Number.isFinite(minutes)?'—':minutes<60?`${Math.max(1,minutes)} min`:minutes<1440?`${Math.floor(minutes/60)} h`:`${Math.floor(minutes/1440)} d`;},canExport:can('reports.export'),canCreate:can('notices.create'),canAssign:can('notices.assign'),canComment:can('notices.comment'),canChangeStatus:can('notices.change_status'),canClose:can('notices.close'),onExport:()=>report('notices',pageQuery('notices',filters.notices)),onStateChange:(values,view,limit)=>{filters.notices={...values,view,limit:limit||filters.notices.limit||50};actions.syncUrl('notices');}};
  }
  if(page==='dashboard'||page==='supervision'){
    if(page==='supervision')return {dashboard:await request('/api/dashboard'),statusLabel};
    const previous=actions.previous||{};
    const [mapResult,geoResult,arrivalOverviewResult]=await Promise.allSettled([
      request('/api/dashboard/map-stats'),
      previous.geo?Promise.resolve(previous.geo):request('/uruguay-departamentos.geojson'),
      can('standards.view')?request('/api/arrival-times/overview'):Promise.resolve(null)
    ]);
    const mapReady=mapResult.status==='fulfilled'&&geoResult.status==='fulfilled';
    return {...common,
      geo:geoResult.status==='fulfilled'?geoResult.value:previous.geo||null,
      mapStats:mapResult.status==='fulfilled'?mapResult.value:previous.mapStats||null,
      mapStatus:mapReady?'ready':'error',
      mapError:mapReady?'':mapResult.status==='rejected'?mapResult.reason.message:geoResult.reason.message,
      arrivalOverview:arrivalOverviewResult.status==='fulfilled'?arrivalOverviewResult.value:null,
      arrivalStatus:arrivalOverviewResult.status==='fulfilled'?'ready':'error',
      arrivalError:arrivalOverviewResult.status==='rejected'?arrivalOverviewResult.reason.message:'',
      canViewArrivalTimes:Boolean(can('standards.view')),
      currentUser,statusLabel};
  }
  if(page==='quotes') return {...common,tab:f.tab,draftKey:`centroQuoteDraft:${actor.id||currentUser}`,canCreate:can('quotes.create'),canExport:can('reports.export'),onExport:values=>report('quotes',query({q:values.search,coverage:values.coverage,mode:values.mode})),onTab:value=>{filters.quotes.tab=value;actions.syncUrl('quotes');}};
  if(page==='delays'){
    if(!can('delays.view'))throw new Error('Acceso denegado a Zonas con demora');
    const [pageData,geography]=await Promise.all([request(`/api/delays?${parameters}`),request('/api/delays/geography')]);
    return {...common,page:pageData,geography,filters:f,viewOptions:[{label:'Vigentes verificadas',value:'active'},{label:'Requieren revisión',value:'review'},{label:'Normalizadas / histórico',value:'history'},{label:'Todas',value:'all'}],departmentOptions:options(Object.keys(geography),'Todos los departamentos',displayLocation),serviceOptions:options(services,'Todas las prestaciones',displayService),canExport:can('reports.export'),canCreate:can('delays.create'),canNormalize:can('delays.normalize'),onApply:values=>update(values),onClear:()=>update({view:'active',from:'',to:'',department:'',service:'',search:''}),onExport:()=>report('delays')};
  }
  if(page==='delayAudit'){
    const pageData=await request(`/api/delays/page?${parameters}`);
    return {...common,page:pageData,filters:f,departments:options(departments,'Todos los departamentos',displayLocation),onPage:(offset,limit=filters.delayAudit.limit||50)=>{filters.delayAudit.limit=limit;return request(`/api/delays/page?${query({...Object.fromEntries(pageQuery('delayAudit',filters.delayAudit)),offset})}`);},onApply:values=>update(values),onClear:()=>update({scope:'all',from:'',to:'',department:'',search:''})};
  }
  if(page==='transfers'){
    const rows=await request(`/api/transfers?${parameters}`);
    return {...common,rows,filters:f,viewOptions:[{label:'Pendientes',value:'active'},{label:'Finalizados',value:'finished'},{label:'Cancelados',value:'cancelled'},{label:'Todos',value:'all'}],statusOptions:options(['SIN_ASIGNAR','ASIGNADO','EN_CURSO','FINALIZADO','CANCELADO'],'Todos los estados').map(item=>({...item,label:item.value?statusLabel(item.value):item.label})),canExport:can('reports.export'),canCreate:can('transfers.create'),canManage:can('transfers.manage'),onApply:values=>update(values),onClear:()=>update({view:'active',from:'',to:'',status:'',type:'',task:'',provider:'',responsible:'',search:''}),onExport:()=>report('transfers')};
  }
  if(page==='schedules'){
    const snapshot=await request(`/api/schedules/team?${parameters}`);
    return {...common,snapshot,userId:actor.id,currentWeek:monday(),filters:f,canRequest:['Telefonista','Planificador','Supervisor'].includes(actor.role_name),onOpenRequests:()=>actions.navigate('requests'),onStateChange:values=>{filters.schedules={...filters.schedules,...values};actions.syncUrl('schedules');}};
  }
  if(page==='requests'){
    if(!['Telefonista','Planificador','Supervisor'].includes(actor.role_name))throw new Error('Las solicitudes no están disponibles para este rol');
    const requests=await request('/api/wfm/requests?scope=mine');
    return {...common,requests,onOpenSchedules:()=>{filters.schedules.view='mine';actions.navigate('schedules');}};
  }
  if(page==='settings'){
    const canManageSettings=Boolean(can('settings.manage'));
    if(!canManageSettings&&!can('arrival_times.manage'))throw new Error('Acceso denegado a Configuración');
    if(!canManageSettings&&f.tab!=='arrival-times')throw new Error('Acceso denegado a esta sección');
    const arrivalFilters=filters.standards;
    const arrivalQuery=offset=>query({department:arrivalFilters.department,service:arrivalFilters.service,is_active:arrivalFilters.status==='active'?true:arrivalFilters.status==='inactive'?false:null,limit:50,offset});
    const [users,roles,permissions,wfmSettings,google,quoteRules,tolls,version,arrivalPage,arrivalGeography]=await Promise.all([f.tab==='users'?request('/api/settings/users'):Promise.resolve([]),['users','roles'].includes(f.tab)?request('/api/settings/roles'):Promise.resolve([]),f.tab==='roles'?request('/api/settings/permissions'):Promise.resolve([]),f.tab==='general'&&actor.role_name==='Administrador'?request('/api/wfm/settings'):null,f.tab==='google'?request('/api/settings/google-access'):null,f.tab==='quotes'?request('/api/settings/quote-rules'):null,f.tab==='catalogs'?request('/api/settings/tolls'):null,f.tab==='news'?request('/api/settings/version'):null,f.tab==='arrival-times'?request(`/api/arrival-times?${arrivalQuery(0)}`):null,f.tab==='arrival-times'?request('/api/arrival-times/geography'):null]);
    const arrivalTimes=f.tab==='arrival-times'?{...common,page:arrivalPage,geography:arrivalGeography,filters:arrivalFilters,canManage:Boolean(can('arrival_times.manage')),onPage:offset=>request(`/api/arrival-times?${arrivalQuery(offset)}`),onApply:values=>{if(generation!==sessionGeneration)return Promise.resolve(false);filters.standards={...filters.standards,...values};actions.syncUrl('settings');return actions.refresh('settings');},onClear:()=>{if(generation!==sessionGeneration)return Promise.resolve(false);filters.standards={department:'',service:'',status:'all'};actions.syncUrl('settings');return actions.refresh('settings');}}:actions.previous?.arrivalTimes||null;
    return {...common,users,roles,permissions,tab:f.tab,wfmSettings,google,quoteRules,tolls,version,arrivalTimes,canManageSettings,canViewArrivalTimes:Boolean(can('standards.view')&&(canManageSettings||can('arrival_times.manage'))),onTab:value=>canManageSettings||value==='arrival-times'?update({tab:value}):Promise.resolve(false),onWfm:()=>actions.navigate('wfm')};
  }
  if(page==='audit'){
    const pageData=await request(`/api/audit/page?${parameters}`);
    return {...common,page:pageData,onPage:(offset,limit=filters.audit.limit||50)=>{filters.audit.limit=limit;return request(`/api/audit/page?${query({...Object.fromEntries(pageQuery('audit',filters.audit)),offset})}`);},filters:f,onApply:values=>update(values),onClear:()=>update({from:'',to:'',entity:'',entityId:'',action:'',actorId:'',search:''}),canExport:can('reports.export'),onExport:()=>report('audit')};
  }
  if(page==='wfm'){
    if(!['Supervisor','Administrador'].includes(actor.role_name))throw new Error('Planificación reservada a supervisores');
    const [plan,requests]=await Promise.all([request(`/api/wfm/plan?date=${f.day}&team=${encodeURIComponent(f.team)}`),request(`/api/wfm/requests?team=${encodeURIComponent(f.team)}`).catch(()=>[])]);
    return {...common,day:f.day,team:f.team,plan,requests,onStateChange:(values,replace=false)=>{filters.wfm={...filters.wfm,...values};actions.syncUrl('wfm',replace);}};
  }
  throw new Error('Pantalla no disponible');
}

const navMain=routes.filter(route=>route.group==='operation').map(route=>route.page);
const navSupervision=routes.filter(route=>route.group==='supervision').map(route=>route.page);
const themeKey='libro-de-trabajo-theme';
function applyTheme(value){const selected=['light','dark','system'].includes(value)?value:'system',dark=selected==='system'?window.matchMedia('(prefers-color-scheme: dark)').matches:selected==='dark';document.documentElement.dataset.themePreference=selected;document.documentElement.dataset.theme=dark?'dark':'light';document.documentElement.classList.toggle('dark',dark);document.documentElement.classList.toggle('tw-dark',dark);document.documentElement.style.colorScheme=dark?'dark':'light';}

export function AppShell(){
  const initialLocation=useRef(null);
  if(!initialLocation.current)initialLocation.current=filtersFromLocation();
  const [actor,setActor]=useState(null),[booting,setBooting]=useState(true),[page,setPage]=useState(initialLocation.current.parsed.route?.page||'__not_found__'),[activeRoute,setActiveRoute]=useState(initialLocation.current.parsed.route),[routeVersion,setRouteVersion]=useState(0),[models,setModels]=useState({}),[loading,setLoading]=useState({}),[errors,setErrors]=useState({}),[profile,setProfile]=useState(false),[logout,setLogout]=useState(false),[supervision,setSupervision]=useState(false),[collapsed,setCollapsed]=useState(()=>localStorage.getItem('sidebarCollapsed')==='true'),[mobile,setMobile]=useState(false),[theme,setTheme]=useState(()=>localStorage.getItem(themeKey)||'system'),[message,setMessage]=useState(null);
  const logoutTrigger = useRef(null);
  const filters=useRef(initialLocation.current.filters),actorRef=useRef(null),pageRef=useRef(initialLocation.current.parsed.route?.page||'__not_found__'),sequence=useRef({}),notificationTimer=useRef(null);
  const modelsRef=useRef({}),dashboardFlight=useRef(null),dashboardQueued=useRef(false),dirtyViews=useRef(new Set());
  const notify=useCallback((value,kind='success')=>{setMessage({value,kind});clearTimeout(notificationTimer.current);notificationTimer.current=setTimeout(()=>setMessage(null),kind==='error'?5500:3200);},[]);
  const navigate=useCallback((next,tab)=>{
    if(next==='settings'&&!actorRef.current?.permissions?.includes('settings.manage')&&actorRef.current?.permissions?.includes('arrival_times.manage'))tab='arrival-times';
    if(next==='settings'&&!tab&&!allowedRoute(routeFor('settings',filters.current.settings.tab),actorRef.current))tab='roles';
    if(tab)filters.current.settings.tab=tab;
    const route=routeFor(next,filters.current.settings.tab);
    if(!route)return;
    const url=routeUrl(route,currentRouteFilters(route,filters.current));
    if(window.location.pathname+window.location.search!==url)window.history.pushState(null,'',url);
    pageRef.current=next;setActiveRoute(route);setPage(next);setMobile(false);setProfile(false);
    if(route.group==='supervision')setSupervision(true);
  },[]);
  const syncUrl=useCallback((target,replace=false)=>{
    if(pageRef.current!==target)return;
    const route=routeFor(target,filters.current.settings.tab);
    if(!route)return;
    const url=routeUrl(route,currentRouteFilters(route,filters.current));
    if(window.location.pathname+window.location.search!==url)window.history[replace?'replaceState':'pushState'](null,'',url);
    setActiveRoute(route);
  },[]);
  const refresh=useCallback((target=pageRef.current)=>{
    const user=actorRef.current;if(!user)return Promise.resolve(false);
    if(target==='dashboard'&&dashboardFlight.current){
      dashboardQueued.current=true;
      sequence.current.dashboard=(sequence.current.dashboard||0)+1;
      return dashboardFlight.current;
    }
    const index=(sequence.current[target]||0)+1;sequence.current[target]=index;
    const generation=sessionGeneration;
    setLoading(current=>({...current,[target]:true}));setErrors(current=>({...current,[target]:null}));
    const task=(async()=>{
      try{
        const model=await loadModel(target,filters.current,user,{refresh,navigate,syncUrl,notify,previous:modelsRef.current[target]});
        if(sequence.current[target]===index&&sessionGeneration===generation){
          dirtyViews.current.delete(target);
          modelsRef.current={...modelsRef.current,[target]:model};
          setModels(current=>({...current,[target]:model}));
        }
        return true;
      }catch(error){
        if(error.stale||sessionGeneration!==generation)return false;
        if(error.status===401){actorRef.current=null;modelsRef.current={};setActor(null);setModels({});return false;}
        if(sequence.current[target]===index)setErrors(current=>({...current,[target]:error.message}));
        return false;
      }finally{if(sequence.current[target]===index&&sessionGeneration===generation)setLoading(current=>({...current,[target]:false}));}
    })();
    if(target==='dashboard'){
      dashboardFlight.current=task;
      task.finally(()=>{
        if(dashboardFlight.current===task)dashboardFlight.current=null;
        if(dashboardQueued.current){
          dashboardQueued.current=false;
          if(pageRef.current==='dashboard'&&document.visibilityState==='visible'&&actorRef.current)refresh('dashboard');
          else setLoading(current=>({...current,dashboard:false}));
        }
      });
    }
    return task;
  },[navigate,syncUrl,notify]);
  useEffect(()=>{window.toast=notify;const parsed=initialLocation.current.parsed;const clean=parsed.route?routeUrl(parsed.route,currentRouteFilters(parsed.route,filters.current)):window.location.pathname;if(window.location.pathname+window.location.search!==clean)window.history.replaceState(null,'',clean);sendRequest('/api/auth/me').then(user=>{actorRef.current=user;setActor(user);}).catch(()=>{actorRef.current=null;setActor(null);}).finally(()=>setBooting(false));return()=>{delete window.toast;clearTimeout(notificationTimer.current);};},[notify]);
  useEffect(()=>{const expired=()=>{invalidateSessionRequests();sequence.current={};dashboardFlight.current=null;dashboardQueued.current=false;dirtyViews.current.clear();actorRef.current=null;modelsRef.current={};setModels({});setLoading({});setErrors({});setMessage(null);setActor(null);setLogout(false);};window.addEventListener('libro:unauthorized',expired);return()=>window.removeEventListener('libro:unauthorized',expired);},[]);
  useEffect(()=>{
    if(!actor||!activeRoute||!allowedRoute(activeRoute,actor))return;
    if(page==='dashboard'){if(document.visibilityState==='visible')refresh('dashboard');}
    else if(!modelsRef.current[page]||dirtyViews.current.has(page))refresh(page);
  },[actor,page,routeVersion,activeRoute,refresh]);
  useEffect(()=>{
    const restore=()=>{
      const parsed=parseRoute(window.location.pathname,window.location.search);
      if(parsed.root)window.history.replaceState(null,'',routeUrl(parsed.route));
      if(parsed.route){
        if(parsed.route.page==='settings'){
          filters.current.settings.tab=parsed.route.tab;
          filters.current.standards={department:'',service:'',status:'all',...(parsed.route.tab==='arrival-times'?parsed.filters:{})};
        } else if(filters.current[parsed.route.page])filters.current[parsed.route.page]={...initialFilters()[parsed.route.page],...parsed.filters};
        const clean=routeUrl(parsed.route,currentRouteFilters(parsed.route,filters.current));
        if(window.location.pathname+window.location.search!==clean)window.history.replaceState(null,'',clean);
        dirtyViews.current.add(parsed.route.page);
        pageRef.current=parsed.route.page;setPage(parsed.route.page);
        if(parsed.route.group==='supervision')setSupervision(true);
      }else{if(window.location.search)window.history.replaceState(null,'',window.location.pathname);pageRef.current='__not_found__';setPage('__not_found__');}
      setActiveRoute(parsed.route);setRouteVersion(value=>value+1);setMobile(false);setProfile(false);
    };
    window.addEventListener('popstate',restore);
    return()=>window.removeEventListener('popstate',restore);
  },[]);
  useEffect(()=>{
    if(!actor||page!=='dashboard')return;
    let timer=null;
    const sync=()=>{
      if(timer){clearInterval(timer);timer=null;}
      if(document.visibilityState==='visible'){
        timer=setInterval(()=>refresh('dashboard'),60000);
      }
    };
    const becameVisible=()=>{const wasHidden=!timer;sync();if(wasHidden&&document.visibilityState==='visible')refresh('dashboard');};
    sync();document.addEventListener('visibilitychange',becameVisible);
    return()=>{if(timer)clearInterval(timer);document.removeEventListener('visibilitychange',becameVisible);};
  },[actor,page,refresh]);
  useEffect(()=>{const changed=event=>{
    const affected=affectedViews(event.detail?.url||'');
    const refreshNow=affected.includes(pageRef.current)&&document.visibilityState==='visible';
    affected.forEach(target=>{
      dirtyViews.current.add(target);
      if(!refreshNow||target!==pageRef.current)sequence.current[target]=(sequence.current[target]||0)+1;
    });
    if(refreshNow)refresh(pageRef.current);
  };window.addEventListener('libro:operational-change',changed);return()=>window.removeEventListener('libro:operational-change',changed);},[refresh]);
  useEffect(()=>{applyTheme(theme);try{localStorage.setItem(themeKey,theme);}catch{}const media=window.matchMedia('(prefers-color-scheme: dark)'),listener=()=>{if(theme==='system')applyTheme('system');};media.addEventListener?.('change',listener);return()=>media.removeEventListener?.('change',listener);},[theme]);
  useEffect(()=>{document.body.classList.toggle('sidebar-collapsed',collapsed);try{localStorage.setItem('sidebarCollapsed',String(collapsed));}catch{}},[collapsed]);
  useEffect(()=>{const viewport=window.matchMedia('(max-width: 900px)'),sync=()=>{document.body.classList.toggle('mobile-viewport',viewport.matches);if(!viewport.matches)setMobile(false);};sync();viewport.addEventListener?.('change',sync);return()=>viewport.removeEventListener?.('change',sync);},[]);
  useEffect(()=>{document.body.classList.toggle('mobile-nav-open',mobile);},[mobile]);
  useEffect(()=>{document.body.classList.toggle('auth-locked',!actor);},[actor]);
  useEffect(()=>{const close=event=>{if(event.key==='Escape'||event.type==='click'&&!(event.target instanceof Element&&event.target.closest('.profile-control')))setProfile(false);};document.addEventListener('click',close);document.addEventListener('keydown',close);return()=>{document.removeEventListener('click',close);document.removeEventListener('keydown',close);};},[]);
  const signIn=async credentials=>{invalidateSessionRequests();await sendRequest('/api/auth/login',{method:'POST',body:JSON.stringify(credentials)});const user=await sendRequest('/api/auth/me');sequence.current={};dashboardFlight.current=null;dashboardQueued.current=false;dirtyViews.current.clear();actorRef.current=user;modelsRef.current={};setModels({});setLoading({});setErrors({});setMessage(null);const location=filtersFromLocation();filters.current=location.filters;const route=location.parsed.route;pageRef.current=route?.page||'__not_found__';setActiveRoute(route);setPage(pageRef.current);setRouteVersion(value=>value+1);setActor(user);};
  const signOut=async()=>{invalidateSessionRequests();await sendRequest('/api/auth/logout',{method:'POST',body:'{}'});sequence.current={};dashboardFlight.current=null;dashboardQueued.current=false;dirtyViews.current.clear();actorRef.current=null;filters.current=initialFilters();modelsRef.current={};setModels({});setLoading({});setErrors({});setMessage(null);setLogout(false);setActor(null);};
  const cancelLogout=()=>{setLogout(false);window.requestAnimationFrame(()=>{if(logoutTrigger.current?.isConnected)logoutTrigger.current.focus();});};
  const can=target=>target==='settings'?routes.some(route=>route.page==='settings'&&allowedRoute(route,actor)):allowedRoute(routeFor(target),actor);
  const visibleSupervision=navSupervision.some(can);
  const firstAllowed=firstAllowedRoute(actor);
  const pageAllowed=allowedRoute(activeRoute,actor);
  const navButton=target=>{
    const route=target==='settings'&&!actor?.permissions?.includes('settings.manage')?routeFor('settings','arrival-times'):routeFor(target,target==='settings'&&allowedRoute(routeFor('settings',filters.current.settings.tab),actor)?filters.current.settings.tab:'roles');
    const href=routeUrl(route,currentRouteFilters(route,filters.current));
    return <a key={target} href={href} data-page={target} className={`${target==='settings'?'settings-button ':''}${page===target?'active ':''}tw-flex tw-items-center tw-gap-2 tw-rounded tw-px-3 tw-py-2 tw-text-[13px] tw-text-blue-100 tw-no-underline hover:tw-bg-slate-800 hover:tw-text-white ${page===target?'tw-bg-blue-800 tw-text-white':''}`} aria-current={page===target?'page':undefined} onClick={event=>{if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;event.preventDefault();navigate(target,route.tab);}}><i className={`pi ${route.icon}`} aria-hidden="true"/><span>{target==='settings'?routeFor('settings').label:route.label}</span></a>;
  };
  if(booting)return <div className="page-loading" role="status">Comprobando sesión…</div>;
  if(!actor)return <LoginView model={{login:signIn}}/>;
  return <><a className="skip-link" href="#content">Saltar al contenido</a>{mobile&&<button className="sidebar-backdrop" aria-label="Cerrar navegación" onClick={()=>setMobile(false)}/>}
    <aside id="sidebar" aria-label="Navegación principal"><div className="sidebar-header"><div className="brand"><img src="/static/libro-trabajo.svg" alt="" width="46" height="46"/><div className="brand-text">Libro de<br/>Trabajo</div></div><button className="sidebar-toggle" type="button" aria-label={collapsed?'Expandir menú':'Contraer menú'} aria-expanded={!collapsed} onClick={()=>setCollapsed(value=>!value)}><i className="pi pi-angle-left"/></button></div><nav aria-label="Operación">{navMain.filter(can).map(navButton)}</nav><div className="sidebar-bottom">{visibleSupervision&&<div className="sidebar-supervision"><button className="sidebar-section-toggle" type="button" aria-expanded={supervision} onClick={()=>setSupervision(value=>!value)}><i className="pi pi-users"/><span>Supervisión</span></button>{supervision&&<div className="sidebar-submenu">{navSupervision.filter(can).map(navButton)}</div>}</div>}{can('settings')&&navButton('settings')}</div></aside>
    <main id="prime-react-root"><header><div className="header-title"><button className="mobile-nav-toggle" type="button" aria-label="Abrir navegación" onClick={()=>setMobile(true)}>☰</button><div><h1>{activeRoute?.title||'Página no encontrada'}</h1></div></div><div className="header-actions"><div className="profile-control"><button className="user-button" type="button" aria-haspopup="dialog" aria-expanded={profile} onClick={()=>setProfile(value=>!value)}><i className="pi pi-user"/><span>{actor.display_name}</span><i className="pi pi-chevron-down profile-chevron"/></button>{profile&&<div className="profile-popover" role="dialog" aria-label="Perfil de usuario"><span>Sesión iniciada como</span><strong>{actor.display_name}</strong><small>{actor.role_name}</small><div className="profile-theme-row"><span>Apariencia</span><label className="theme-native-control"><i className="pi pi-palette"/><select aria-label="Cambiar tema visual" value={theme} onChange={event=>setTheme(event.target.value)}><option value="light">Claro</option><option value="dark">Oscuro</option><option value="system">Sistema</option></select></label></div></div>}</div><button className="logout-button tw-text-red-600 tw-bg-red-50 hover:tw-bg-red-100" type="button" onClick={event=>{logoutTrigger.current=event.currentTarget;setLogout(true);}}><i className="pi pi-sign-out"/><span>Salir</span></button></div></header>
      <section id="content" role="region" tabIndex="-1">{!activeRoute?<div className="tw-rounded-md tw-border tw-border-app-border tw-bg-app-surface tw-p-4" role="alert"><strong>Página no encontrada</strong><p>La dirección solicitada no corresponde a una sección de la herramienta.</p>{firstAllowed&&<Button label={`Ir a ${firstAllowed.label}`} onClick={()=>navigate(firstAllowed.page,firstAllowed.tab)}/>}</div>:!pageAllowed?<div className="tw-rounded-md tw-border tw-border-app-border tw-bg-app-surface tw-p-4" role="alert"><strong>Acceso no permitido</strong><p>No tenés permiso para abrir esta sección.</p>{firstAllowed&&<Button label={`Ir a ${firstAllowed.label}`} onClick={()=>navigate(firstAllowed.page,firstAllowed.tab)}/>}</div>:<>{Object.keys(models).map(target=>{const View=memoizedComponents[target],viewModel=target==='dashboard'?{...models[target],refreshing:Boolean(loading.dashboard)}:models[target];return <div key={target} data-view={target} className={`operational-view tw-min-w-0 tw-w-full ${page!==target?'tw-hidden':''}`} hidden={page!==target} aria-hidden={page!==target}><View model={viewModel} active={page===target}/></div>;})}{loading[page]&&!models[page]&&<div className="page-loading tw-flex tw-items-center tw-gap-3" role="status"><ProgressSpinner style={{width:28,height:28}} strokeWidth="5"/>Cargando información…</div>}{errors[page]&&<div className="panel empty load-error" role="alert"><strong>No se pudo cargar esta pantalla</strong><p>{errors[page]}</p><Button label="Reintentar" onClick={()=>refresh(page)}/></div>}</>}</section>
    </main>{logout&&<LogoutDialog model={{confirm:signOut,cancel:cancelLogout}}/>}{message&&<div id="toast" className={`show ${message.kind}`} role={message.kind==='error'?'alert':'status'}>{message.value}</div>}</>;
}
