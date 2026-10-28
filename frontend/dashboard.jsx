import React, { useEffect, useState } from 'react';
import { Button } from 'primereact/button';
import { Card } from 'primereact/card';
import { Tag } from 'primereact/tag';
import { formatDateTime } from './date-format.js';
import { displayLocation, displayService } from './operational-labels.js';
import { departmentAt, nextReviewDeadline } from './delay-map-state.js';
import { arrivalDelayText, arrivalIndicationCompact, departmentArrivalRows } from './arrival-map-query.js';

const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toUpperCase();
const activeDelayColor = '#ef4444';
const reviewDelayColor = '#b91c1c';
const fmt = formatDateTime;
const cardStyle = 'tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm dark:tw-border-slate-700 dark:tw-bg-slate-800';
export function geoPath(geometry) {
  const project = ([lon, lat]) => [20 + (lon + 58.65) / 5.75 * 380, 20 + (-29.95 - lat) / 5.25 * 460];
  const polygon = rings => rings.map(ring => ring.map((point, i) => { const [x, y] = project(point); return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`; }).join('') + 'Z').join('');
  if (geometry.type === 'Polygon') return polygon(geometry.coordinates);
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.map(polygon).join('');
  return '';
}

function ArrivalLine({ row }) {
  const { situation } = row;
  const affected = ['exception', 'review', 'overlap'].includes(situation.state);
  const uncertain = ['review', 'overlap', 'unverified', 'missing'].includes(situation.state);
  const answer = situation.state === 'exception' ? `Demora activa: ${situation.answer}`
    : situation.state === 'review' ? 'Demora activa · verificar antes de confirmar'
    : situation.state === 'overlap' ? 'Demoras superpuestas · confirmar con Planificación'
    : situation.state === 'habitual' || situation.state === 'unconfirmed' ? arrivalIndicationCompact(row.standard)
    : situation.state === 'missing' ? 'Sin estándar configurado' : 'Información no disponible';
  return <div className={'tw-grid tw-min-w-0 tw-gap-1 tw-rounded tw-border tw-p-2 ' + (affected ? 'tw-border-red-300 tw-bg-red-50 dark:tw-border-red-800 dark:tw-bg-red-950/30' : uncertain ? 'tw-border-amber-200 tw-bg-amber-50 dark:tw-border-amber-800 dark:tw-bg-amber-950/20' : 'tw-border-slate-200 tw-bg-blue-50/50 dark:tw-border-slate-700 dark:tw-bg-slate-900')}>
    <div className="tw-flex tw-min-w-0 tw-items-start tw-justify-between tw-gap-2"><span className="tw-min-w-0 tw-break-words tw-text-xs tw-font-medium">{displayLocation(row.label)}</span><Tag value={affected ? situation.state === 'review' ? 'Revisión pendiente' : 'Demora activa' : situation.state === 'unconfirmed' ? 'A confirmar' : uncertain ? 'No confirmado' : 'Habitual'} severity={affected ? situation.state === 'review' || situation.state === 'overlap' ? 'warning' : 'danger' : uncertain || situation.state === 'unconfirmed' ? 'secondary' : 'info'} /></div>
    <strong className="tw-break-words tw-text-sm">{answer}</strong>
    {situation.state === 'review' && situation.matching.map(item => <small key={item.id}>Indicación anterior: {arrivalDelayText(item)} · Última verificación: {fmt(item.last_verified_at)}</small>)}
    {situation.state === 'overlap' && situation.matching.map(item => <small key={item.id}>{displayService(item.service)} · {displayLocation(item.zone)}: {arrivalDelayText(item)}</small>)}
    {situation.state === 'exception' && situation.matching[0]?.instruction_text && situation.matching[0].message !== 'Otra indicación' && <small>{situation.matching[0].instruction_text}</small>}
    {situation.state === 'exception' && situation.answer.startsWith('Margen de') && <small>El margen no define un tiempo total de llegada.</small>}
  </div>;
}

function Map({ geo, mapStats, status, refreshing, onRetry, arrivalOverview, arrivalStatus, arrivalError, canViewArrivalTimes }) {
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
  const selectedData = byName[selected];
  const departmentLabel = selectedData?.department || Object.keys(arrivalOverview?.departments || {}).find(name => normalize(name) === selected) || selected;
  const services = ['ML', 'GRÚA', 'SINIESTROS'];
  const arrivalItems = arrivalOverview?.departments?.[departmentLabel] || [];
  const consultationStatus = refreshing ? 'loading' : status === 'ready' && !selectedData ? 'error' : status;
  const results = services.map(service => ({ service, rows: departmentArrivalRows({
    items: arrivalItems, delays: selectedData?.delays || [], service,
    mapStatus: consultationStatus, standardStatus: canViewArrivalTimes ? arrivalStatus : 'error',
  }) }));

  if (!geo) return <div className="tw-flex tw-flex-col tw-items-start tw-gap-3 tw-p-4" role="alert"><strong>Información del mapa no disponible.</strong><Button label="Reintentar" size="small" onClick={onRetry}/></div>;
  return <div className="tw-grid tw-min-w-0 tw-gap-3 xl:tw-grid-cols-[minmax(0,1fr)_minmax(360px,0.9fr)]">
    <div className="uruguay-map-wrap tw-grid-cols-1 tw-min-w-0 tw-self-start tw-rounded-md tw-border tw-border-slate-200 tw-bg-slate-50 tw-p-3 dark:tw-border-slate-700 dark:tw-bg-slate-900">
      <div className="map-canvas tw-mx-auto tw-w-full tw-max-w-[500px]"><svg className="uruguay-map" viewBox="0 0 420 500" role="img" aria-label="Mapa de Uruguay: tiempos de llegada y demoras por departamento"><g className="country-shape">{(geo.features || []).filter(feature => !['ISLA BRASILENA', 'RINCON DE MANECO'].includes(normalize(feature.properties.nam || feature.properties.DEPTO))).map(feature => {
        const raw = feature.properties.nam || feature.properties.DEPTO || '', name = normalize(raw), data = byName[name], count = data?.active_count || 0, due = data?.review_due_count || 0;
        const fill = status === 'error' ? '#cbd5e1' : count === 0 ? '#dbeafe' : due > 0 ? reviewDelayColor : activeDelayColor;
        const description = status === 'error' ? 'Información no disponible' : count ? (due ? 'Demoras que requieren revisión' : 'Demoras vigentes') : 'Sin demoras vigentes';
        return <path key={name} d={geoPath(feature.geometry)} fill={fill} className={'map-department ' + (count && status !== 'error' ? 'has-active' : '')} role="button" tabIndex={0} aria-pressed={selected === name} aria-label={displayLocation(raw) + ': ' + description + '. Consultar llegada'} onClick={() => setSelected(name)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelected(name); } }}><title>{displayLocation(raw)}: {description}</title></path>;
      })}</g></svg></div>
      <div className="tw-mt-2 tw-flex tw-flex-wrap tw-items-center tw-gap-x-3 tw-gap-y-1 tw-text-xs"><span><i className="tw-mr-1 tw-inline-block tw-h-3 tw-w-3 tw-rounded-sm tw-bg-blue-100"/>Sin demoras vigentes</span><span><i className="tw-mr-1 tw-inline-block tw-h-3 tw-w-3 tw-rounded-sm tw-bg-red-500"/>Demora vigente</span><span><i className="tw-mr-1 tw-inline-block tw-h-3 tw-w-3 tw-rounded-sm tw-bg-red-700"/>Requiere revisión</span>{status === 'error' && <span><i className="tw-mr-1 tw-inline-block tw-h-3 tw-w-3 tw-rounded-sm tw-bg-slate-400"/>Información no disponible</span>}</div>
    </div>
    <section role="complementary" aria-label="Consulta de llegada" className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-p-4 dark:tw-border-slate-700 dark:tw-bg-slate-800">
      {!selected ? <div className="tw-flex tw-min-h-48 tw-flex-col tw-justify-center tw-gap-2"><h2 className="tw-m-0 tw-text-base tw-font-semibold">Consulta de llegada</h2><p className="tw-m-0 tw-text-sm tw-text-app-muted">Seleccioná un departamento en el mapa para ver qué indicar al cliente.</p></div> : <>
        <div className="tw-mb-3 tw-flex tw-items-center tw-justify-between tw-gap-2"><h2 className="tw-m-0 tw-text-base tw-font-semibold">{displayLocation(departmentLabel)}</h2>{refreshing && <small role="status">Actualizando…</small>}</div>
        {status === 'error' && <div role="alert" className="tw-mb-3 tw-rounded tw-border tw-border-amber-500 tw-p-2">No se pudieron confirmar las demoras actuales. <Button label="Reintentar" text size="small" onClick={onRetry}/></div>}
        {!canViewArrivalTimes && <div role="alert" className="tw-mb-3">No tenés acceso a los tiempos estándar. Pedí una referencia confirmada.</div>}
        {canViewArrivalTimes && arrivalStatus === 'error' && <div role="alert" className="tw-mb-3 tw-rounded tw-border tw-border-amber-500 tw-p-2">{arrivalError || 'No se pudieron confirmar los tiempos estándar.'} <Button label="Reintentar" text size="small" onClick={onRetry}/></div>}
        <div className="tw-grid tw-gap-2" role="group" aria-label="Indicaciones por prestación">{results.map(({ service, rows }) => {
          const affected = rows.some(row => ['exception', 'review', 'overlap'].includes(row.situation.state));
          return <Card key={service} className={'tw-min-w-0 tw-border ' + (affected ? 'tw-border-red-300 tw-bg-red-50/40 dark:tw-border-red-800 dark:tw-bg-slate-900' : 'tw-border-slate-200 dark:tw-border-slate-700 dark:tw-bg-slate-900')} pt={{body:{className:'tw-p-3'},content:{className:'tw-p-0'}}}>
            <section aria-label={displayService(service)} className="tw-min-w-0"><h3 className="tw-m-0 tw-mb-2 tw-text-sm tw-font-semibold">{displayService(service)}</h3>
              <div className="tw-grid tw-gap-1">{rows.map((row, index) => <ArrivalLine key={`${service}-${index}`} row={row}/>)}</div>
            </section>
          </Card>;
        })}</div>
      </>}
    </section>
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

export function DashboardView({ model, active = true }) {
  const { geo, mapStats, mapStatus, refreshing } = model;
  return <div className="operational-view dashboard-react-view tw-grid tw-min-w-0 tw-gap-3 tw-bg-app-canvas tw-text-[13px]">
    <div className="tw-flex tw-w-full tw-flex-wrap tw-items-center tw-gap-3 tw-text-xs" role="status"><span>Mapa: {mapStats?.as_of?fmt(mapStats.as_of):'sin actualización confirmada'}{mapStatus==='error'?' · datos desactualizados':''}</span>{refreshing&&<span>Actualizando…</span>}</div>
    <div className="tw-grid tw-min-w-0 tw-gap-3">
      <Card className={cardStyle} title="Consulta de llegada por departamento" pt={{body:{className:'tw-p-3'}}}>
        {mapStatus==='error'&&<div className="tw-mb-3 tw-flex tw-flex-wrap tw-items-center tw-gap-3 tw-rounded tw-border tw-border-amber-500 tw-p-3" role="alert"><strong>{mapStats?'Mapa desactualizado':'Información del mapa no disponible'}</strong><span>{model.mapError}</span><Button label="Reintentar" size="small" onClick={model.refresh}/></div>}
        <Map geo={geo} mapStats={mapStats} status={mapStatus} refreshing={refreshing} onRetry={model.refresh} arrivalOverview={model.arrivalOverview} arrivalStatus={model.arrivalStatus} arrivalError={model.arrivalError} canViewArrivalTimes={model.canViewArrivalTimes}/>
      </Card>
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
