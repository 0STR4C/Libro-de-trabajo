import React, { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Card } from 'primereact/card';
import { OverlayPanel } from 'primereact/overlaypanel';
import { Tag } from 'primereact/tag';
import { formatDateTime } from './date-format.js';
import { departmentAt, nextReviewDeadline } from './delay-map-state.js';

const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toUpperCase();
const verifiedColors = ['#dbeafe', '#bfdbfe', '#93c5fd', '#60a5fa', '#2563eb'];
const reviewColors = ['#fef3c7', '#fde68a', '#fcd34d', '#fbbf24', '#d97706'];
const fmt = formatDateTime;
const cardStyle = 'tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm dark:tw-border-slate-700 dark:tw-bg-slate-800';
const delayGuidance = item => {
  if (item.needs_review) {
    if (item.message === 'Margen de') return 'Margen informado anteriormente. Verificar antes de comunicar un tiempo.';
    if (item.message === 'A confirmar') return 'Tiempo pendiente de confirmación. Verificar el estado actual.';
    return `${item.message || 'Demora registrada'}. Verificar antes de comunicar.`;
  }
  return item.message === 'Margen de' && item.minutes ? `Margen comunicado: ${item.minutes} min` : item.message || 'Tiempo por confirmar';
};

export function geoPath(geometry) {
  const project = ([lon, lat]) => [20 + (lon + 58.65) / 5.75 * 380, 20 + (-29.95 - lat) / 5.25 * 460];
  const polygon = rings => rings.map(ring => ring.map((point, i) => { const [x, y] = project(point); return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`; }).join('') + 'Z').join('');
  if (geometry.type === 'Polygon') return polygon(geometry.coordinates);
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.map(polygon).join('');
  return '';
}

function Map({ geo, mapStats, status, onRetry }) {
  const overlay = useRef(null);
  const popupAnchor = useRef(null);
  const [selected, setSelected] = useState('');
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    let timer;
    const schedule = () => {
      const current = Date.now();
      setNow(current);
      const deadline = nextReviewDeadline(mapStats, current);
      if (deadline !== null) timer = window.setTimeout(schedule, Math.max(1, deadline - current + 1));
    };
    schedule();
    const becameVisible = () => { if (document.visibilityState === 'visible') setNow(Date.now()); };
    document.addEventListener('visibilitychange', becameVisible);
    return () => { window.clearTimeout(timer); document.removeEventListener('visibilitychange', becameVisible); };
  }, [mapStats]);
  const departments = (mapStats?.departments || []).map(item => departmentAt(item, now));
  const byName = Object.fromEntries(departments.map(item => [normalize(item.department), item]));
  const max = Math.max(1, ...departments.map(item => item.active_count || 0));
  const selectedData = byName[selected];
  const show = (event, name) => {
    const pointer = event.nativeEvent || event.originalEvent || event;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = pointer.detail === 0 || pointer.type === 'keydown' ? bounds.left + bounds.width / 2 : pointer.clientX;
    const y = pointer.detail === 0 || pointer.type === 'keydown' ? bounds.top + bounds.height / 2 : pointer.clientY;
    popupAnchor.current.style.left = `${x}px`;
    popupAnchor.current.style.top = `${y}px`;
    setSelected(name);
    overlay.current?.show(pointer, popupAnchor.current);
  };
  if(!geo)return <div className="tw-flex tw-flex-col tw-items-start tw-gap-3 tw-p-4" role="alert"><strong>Información del mapa no disponible.</strong><Button label="Reintentar" size="small" onClick={onRetry}/></div>;
  return <div className="uruguay-map-wrap tw-min-w-0">
    <span ref={popupAnchor} className="map-popup-anchor" aria-hidden="true" />
    <div className="map-canvas"><svg className="uruguay-map" viewBox="0 0 420 500" role="img" aria-label="Mapa de Uruguay con demoras por departamento"><g className="country-shape">{(geo.features || []).filter(feature => !['ISLA BRASILENA', 'RINCON DE MANECO'].includes(normalize(feature.properties.nam || feature.properties.DEPTO))).map(feature => {
      const raw=feature.properties.nam||feature.properties.DEPTO||'',name=normalize(raw),data=byName[name],count=data?.active_count||0,due=data?.review_due_count||0;
      const level=Math.max(0,Math.min(4,Math.ceil(count/max*5)-1));
      const fill=status==='error'?'#cbd5e1':count===0?'#e2e8f0':due>0?reviewColors[level]:verifiedColors[level];
      const description=status==='error'?'Información no disponible':`${data?.verified_count||0} vigentes verificadas; ${due} requieren revisión`;
      return <path key={name} d={geoPath(feature.geometry)} fill={fill} className={`map-department ${count&&status!=='error'?'has-active':''}`} role="button" tabIndex={0} aria-label={`${raw}: ${description}. Ver detalle`} onClick={event=>show(event,name)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();show(event,name);}}}><title>{raw}: {description}</title></path>;
    })}</g></svg></div>
    <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-3 tw-text-xs"><span><i className="tw-mr-1 tw-inline-block tw-h-3 tw-w-3 tw-rounded-sm tw-bg-slate-200"/>Sin demoras vigentes</span><span><i className="tw-mr-1 tw-inline-block tw-h-3 tw-w-3 tw-rounded-sm tw-bg-blue-500"/>Vigente verificada</span><span><i className="tw-mr-1 tw-inline-block tw-h-3 tw-w-3 tw-rounded-sm tw-bg-amber-500"/>Requiere revisión</span>{status==='error'&&<span><i className="tw-mr-1 tw-inline-block tw-h-3 tw-w-3 tw-rounded-sm tw-bg-slate-400"/>Información no disponible</span>}</div>
    <OverlayPanel ref={overlay} appendTo={document.body} className="delay-map-overlay" dismissable>
      <div className="tw-flex tw-max-w-[min(440px,90vw)] tw-flex-col tw-gap-2 tw-text-[13px]">
        <strong>{selectedData?.department||selected}</strong>
        {status==='error'&&<div className="tw-rounded tw-border tw-border-amber-500 tw-p-2" role="alert">Información desactualizada: no confirmes tiempos hasta reintentar. <Button label="Reintentar" text size="small" onClick={onRetry}/></div>}
        {!selectedData?.active_count ? <p>{status==='error'?'Información no disponible.':'Sin demoras vigentes registradas.'}</p> : <>
          <div className="tw-flex tw-flex-wrap tw-gap-2"><Tag value={`${selectedData.verified_count} ${status==='error'?'verificadas en la última lectura':'vigentes verificadas'}`} severity="info"/><Tag value={`${selectedData.review_due_count} requieren revisión`} severity={selectedData.review_due_count?'warning':'success'}/></div>
          <ul className="tw-m-0 tw-flex tw-max-h-[55vh] tw-flex-col tw-gap-2 tw-overflow-y-auto tw-p-0 tw-list-none">{(selectedData.delays||[]).map(item=><li key={item.id} className="tw-rounded tw-border tw-border-[var(--border)] tw-p-2">
            <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-2"><strong className="tw-whitespace-normal tw-break-words">{item.zone} · {item.service}</strong><Tag value={status==='error'?'Lectura desactualizada':item.needs_review?'Requiere revisión':'Vigente verificada'} severity={status==='error'||item.needs_review?'warning':'success'}/></div>
            <div className="tw-whitespace-normal tw-break-words">{delayGuidance(status==='error'?{...item,needs_review:true}:item)}</div>
            <small className="tw-block">Última verificación: {item.last_verified_at?fmt(item.last_verified_at):'Sin verificación registrada'}</small>
            {item.needs_review&&<small className="tw-block">Revisión vencida: {fmt(item.review_due_at)}</small>}
          </li>)}</ul>
        </>}
      </div>
    </OverlayPanel>
  </div>;
}

function Bars({ counts, limit = 5 }) {
  const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]).slice(0, limit);
  const max = Math.max(1, ...entries.map(([, value]) => value));
  if (!entries.length) return <div className="empty">Todavía no hay datos.</div>;
  return <div className="metric-bars">{entries.map(([name, value]) => <div className="metric-bar-row" key={name}><div className="metric-bar-label"><span>{name}</span><strong>{value}</strong></div><div className="metric-track"><i style={{ width: `${Math.max(5, value / max * 100)}%` }} /></div></div>)}</div>;
}

function Metric({ label, value, note }) {
  return <Card className={cardStyle} pt={{ body: { className: 'tw-p-3' } }}><div className="tw-grid tw-gap-1"><span className="tw-text-xs tw-text-slate-500">{label}</span><strong className="tw-text-2xl">{value}</strong>{note && <small>{note}</small>}</div></Card>;
}

function Section({ priority, title, children }) {
  return <section className={`dashboard-priority dashboard-priority-${priority}`} aria-label={title}><div className="tw-mb-2 tw-flex tw-items-center tw-gap-2"><h2 className="tw-m-0 tw-text-sm tw-font-semibold">{title}</h2></div>{children}</section>;
}

export function DashboardView({ model }) {
  const { geo, mapStats, mapStatus, alerts = [], alertsStatus, showAlerts, refreshing } = model;
  const [alertScope, setAlertScope] = useState('all');
  const visibleAlerts = alertScope === 'mine' ? alerts.filter(item => normalize(item.responsible) === normalize(model.currentUser)) : alerts;
  return <div className="operational-view dashboard-react-view tw-grid tw-min-w-0 tw-gap-3 tw-bg-app-canvas tw-text-[13px]">
    <div className="tw-flex tw-w-full tw-flex-wrap tw-items-center tw-gap-3 tw-text-xs" role="status"><span>Mapa: {mapStats?.as_of?fmt(mapStats.as_of):'sin actualización confirmada'}{mapStatus==='error'?' · datos desactualizados':''}</span>{showAlerts&&<span>Alertas: {model.alertsUpdatedAt?fmt(model.alertsUpdatedAt):'sin actualización confirmada'}{alertsStatus==='error'?' · datos desactualizados':''}</span>}{refreshing&&<span>Actualizando…</span>}</div>
    <div className="tw-grid tw-min-w-0 tw-gap-3 xl:tw-grid-cols-[minmax(0,1.55fr)_minmax(300px,0.65fr)]">
      <Card className={cardStyle} title="Demoras vigentes por departamento" pt={{body:{className:'tw-p-3'}}}>
        {mapStatus==='error'&&<div className="tw-mb-3 tw-flex tw-flex-wrap tw-items-center tw-gap-3 tw-rounded tw-border tw-border-amber-500 tw-p-3" role="alert"><strong>{mapStats?'Mapa desactualizado':'Información del mapa no disponible'}</strong><span>{model.mapError}</span><Button label="Reintentar" size="small" onClick={model.refresh}/></div>}
        <Map geo={geo} mapStats={mapStats} status={mapStatus} onRetry={model.refresh}/>
      </Card>
      {showAlerts&&<Card className={cardStyle} title="Alertas operativas" pt={{body:{className:'tw-p-3'}}}>
        <div className="tw-mb-3 tw-flex tw-flex-wrap tw-items-center tw-gap-3 tw-w-full"><Button label="Todas" text={alertScope!=='all'} size="small" onClick={()=>setAlertScope('all')}/><Button label="Asignadas a mí" text={alertScope!=='mine'} size="small" onClick={()=>setAlertScope('mine')}/></div>
        {refreshing&&<div className="tw-mb-2" role="status">Consultando alertas…</div>}
        {alertsStatus==='error'&&<div className="tw-mb-3 tw-flex tw-flex-wrap tw-items-center tw-gap-3 tw-rounded tw-border tw-border-amber-500 tw-p-3" role="alert"><strong>{model.alertsUpdatedAt?'Alertas desactualizadas':'Información de alertas no disponible'}</strong><span>{model.alertsError}</span><Button label="Reintentar" size="small" onClick={model.refresh}/></div>}
        {alertsStatus==='empty'?<div className="empty">No hay alertas operativas.</div>:visibleAlerts.length?visibleAlerts.map((item,index)=><div className="operational-alert" key={`${item.kind}-${item.entity_id||index}`}><Tag value={item.kind==='DELAY'?'Demora':item.kind==='STANDARD_APPROVAL'?'Aprobación':'Revisión'} severity={item.severity==='OVERDUE'?'danger':'warning'}/><strong>{item.title}</strong><small>{item.responsible} · {fmt(item.due_at)}</small>{alertsStatus==='error'&&<small>Dato desactualizado</small>}</div>):alertsStatus==='error'?<div>No se pudo confirmar si hay alertas.</div>:alertScope==='mine'?<div className="empty">No hay alertas asignadas a mí.</div>:null}
      </Card>}
    </div>
  </div>;
}

export function SupervisionDashboardView({ model }) {
  const d=model.dashboard,distributions=d.distributions||{};
  const departments=Object.fromEntries((distributions.delays_by_department||[]).map(item=>[item.department,item.count]));
  const notices=Object.fromEntries(Object.entries(distributions.notices_by_status||{}).map(([status,count])=>[model.statusLabel(status),count]));
  const transfers=Object.fromEntries(Object.entries(distributions.transfers_by_status||{}).map(([status,count])=>[model.statusLabel(status),count]));
  return <div className="operational-view tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]"><div className="dashboard-as-of">Período de análisis: {d.period_days||30} días · actualizado {fmt(d.as_of)}</div>
    <div className="tw-grid tw-gap-3 sm:tw-grid-cols-2 xl:tw-grid-cols-4"><Metric label="Avisos abiertos" value={d.notices_open}/><Metric label="Programados pendientes" value={d.transfers_pending}/><Metric label="Demoras vigentes" value={d.delays_current}/><Metric label="Demoras a revisar" value={d.delays_need_review}/></div>
    <div className="tw-grid tw-gap-3 lg:tw-grid-cols-3"><Card className={cardStyle} title="Avisos por estado"><Bars counts={notices}/></Card><Card className={cardStyle} title="Programados por estado"><Bars counts={transfers}/></Card><Card className={cardStyle} title="Demoras por departamento"><Bars counts={departments}/></Card></div>
  </div>;
}
