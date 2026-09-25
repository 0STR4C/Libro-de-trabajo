import React, { useRef, useState } from 'react';
import { Card } from 'primereact/card';
import { OverlayPanel } from 'primereact/overlaypanel';
import { Tag } from 'primereact/tag';

const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toUpperCase();
const colors = ['#eef5fb', '#dcecf8', '#bddcf1', '#8fc2e3', '#5aa2cf', '#267bb3'];
const neighbors = { ARTIGAS: ['SALTO', 'RIVERA'], CANELONES: ['MONTEVIDEO', 'SAN JOSE', 'FLORIDA', 'LAVALLEJA', 'MALDONADO'], 'CERRO LARGO': ['RIVERA', 'TACUAREMBO', 'DURAZNO', 'TREINTA Y TRES'], COLONIA: ['SORIANO', 'FLORES', 'SAN JOSE'], DURAZNO: ['TACUAREMBO', 'CERRO LARGO', 'TREINTA Y TRES', 'FLORIDA', 'FLORES', 'RIO NEGRO'], FLORES: ['SORIANO', 'RIO NEGRO', 'DURAZNO', 'FLORIDA', 'SAN JOSE', 'COLONIA'], FLORIDA: ['DURAZNO', 'TREINTA Y TRES', 'LAVALLEJA', 'CANELONES', 'SAN JOSE', 'FLORES'], LAVALLEJA: ['TREINTA Y TRES', 'ROCHA', 'MALDONADO', 'CANELONES', 'FLORIDA'], MALDONADO: ['LAVALLEJA', 'ROCHA', 'CANELONES'], MONTEVIDEO: ['CANELONES', 'SAN JOSE'], PAYSANDU: ['SALTO', 'TACUAREMBO', 'RIO NEGRO'], 'RIO NEGRO': ['PAYSANDU', 'TACUAREMBO', 'DURAZNO', 'FLORES', 'SORIANO'], RIVERA: ['ARTIGAS', 'SALTO', 'TACUAREMBO', 'CERRO LARGO'], ROCHA: ['TREINTA Y TRES', 'LAVALLEJA', 'MALDONADO'], SALTO: ['ARTIGAS', 'RIVERA', 'TACUAREMBO', 'PAYSANDU'], 'SAN JOSE': ['COLONIA', 'FLORES', 'FLORIDA', 'CANELONES', 'MONTEVIDEO'], SORIANO: ['RIO NEGRO', 'FLORES', 'COLONIA'], TACUAREMBO: ['RIVERA', 'SALTO', 'PAYSANDU', 'RIO NEGRO', 'DURAZNO', 'CERRO LARGO'], 'TREINTA Y TRES': ['CERRO LARGO', 'DURAZNO', 'FLORIDA', 'LAVALLEJA', 'ROCHA'] };
const fmt = value => value ? new Date(value).toLocaleString('es-UY', { dateStyle: 'short', timeStyle: 'short' }) : '—';
const cardStyle = 'tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm dark:tw-border-slate-700 dark:tw-bg-slate-800';

export function geoPath(geometry) {
  const project = ([lon, lat]) => [20 + (lon + 58.65) / 5.75 * 380, 20 + (-29.95 - lat) / 5.25 * 460];
  const polygon = rings => rings.map(ring => ring.map((point, i) => { const [x, y] = project(point); return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`; }).join('') + 'Z').join('');
  if (geometry.type === 'Polygon') return polygon(geometry.coordinates);
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.map(polygon).join('');
  return '';
}

function Map({ geo, departments, activeDelays }) {
  const overlay = useRef(null);
  const popupAnchor = useRef(null);
  const [selected, setSelected] = useState('');
  const counts = Object.fromEntries(departments.map(item => [normalize(item.department), Number(item.count || 0)]));
  const scores = Object.fromEntries(Object.keys(counts).map(name => [name, counts[name] + (neighbors[name] || []).reduce((sum, neighbor) => sum + (counts[neighbor] || 0) * .7, 0)]));
  const max = Math.max(1, ...Object.values(scores));
  const selectedRows = activeDelays.filter(item => normalize(item.department) === selected).sort((a, b) => String(a.zone).localeCompare(String(b.zone), 'es'));
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
  return <div className="uruguay-map-wrap"><span ref={popupAnchor} className="map-popup-anchor" aria-hidden="true" /><div className="map-canvas"><svg className="uruguay-map" viewBox="0 0 420 500" role="img" aria-label="Mapa de Uruguay con demoras vigentes por departamento"><g className="country-shape">{(geo?.features || []).filter(feature => !['ISLA BRASILENA', 'RINCON DE MANECO'].includes(normalize(feature.properties.nam || feature.properties.DEPTO))).map((feature, index) => { const raw = feature.properties.nam || feature.properties.DEPTO || '', name = normalize(raw), count = counts[name] || 0, level = count ? Math.max(1, Math.min(colors.length - 1, Math.ceil(scores[name] / max * (colors.length - 1)))) : 0; return <path key={name} d={geoPath(feature.geometry)} fill={colors[level]} className={`map-department ${count ? 'has-active' : ''}`} role="button" tabIndex={0} aria-label={`${raw}: ${count} ${count === 1 ? 'demora vigente' : 'demoras vigentes'}. Ver detalle`} onClick={event => show(event, name)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); show(event, name); } }}><title>{raw}: {count} {count === 1 ? 'demora vigente' : 'demoras vigentes'}</title></path>; })}</g></svg></div><div className="map-legend"><span>Sin demora vigente</span>{colors.map(color => <i key={color} style={{ background: color }} />)}<span>Mayor concentración regional</span></div><OverlayPanel ref={overlay} appendTo={document.body} className="delay-map-overlay" dismissable><strong>{selected}</strong>{selectedRows.length ? <ul>{selectedRows.map(item => <li key={item.id}><span>{item.zone || 'Zona no especificada'} · {item.service}</span><b>{item.message === 'Margen de' && item.minutes ? `${item.minutes} min` : item.message || 'Tiempo por confirmar'}</b></li>)}</ul> : <p>Sin demoras vigentes verificadas.</p>}</OverlayPanel></div>;
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
  const { dashboard: d, geo, activeDelays = [], alerts = [], showAlerts } = model;
  const [alertScope, setAlertScope] = useState('all');
  const distributions = d.distributions || {}, departmentRows = distributions.delays_by_department || [];
  const departmentCounts = Object.fromEntries(departmentRows.map(item => [item.department, item.count]));
  const visibleAlerts = alertScope === 'mine' ? alerts.filter(item => item.responsible === model.currentUser) : alerts;
  const noticeStates = Object.fromEntries(Object.entries(distributions.notices_by_status || {}).map(([status, count]) => [model.statusLabel(status), count]));
  const transferStates = Object.fromEntries(Object.entries(distributions.transfers_by_status || {}).map(([status, count]) => [model.statusLabel(status), count]));
  return <div className="operational-view dashboard-react-view tw-grid tw-min-w-0 tw-gap-3 tw-bg-app-canvas tw-text-[13px]"><div className="dashboard-as-of">Estado calculado al {fmt(d.as_of)} <small>{d.timezone} · definiciones v{d.definitions_version}</small></div>
    <Section priority={1} title="Mapa y demoras"><div className="dashboard-priority-top tw-grid tw-gap-3 xl:tw-grid-cols-[minmax(0,1.45fr)_minmax(280px,0.75fr)]"><Card className={cardStyle} title="Demoras verificadas por departamento" pt={{ body: { className: 'tw-p-3' } }}><Map geo={geo} departments={departmentRows} activeDelays={activeDelays} /></Card><div className="dashboard-priority-side tw-grid tw-gap-3"><Metric label="Demoras verificadas" value={d.delays_current} note={d.delays_need_review ? `${d.delays_need_review} requieren revisión` : 'Todas tienen revisión vigente'} /><Card className={cardStyle} title="Departamentos afectados ahora"><Bars counts={departmentCounts} /></Card><Card className={cardStyle} title="Estado de avisos abiertos"><Bars counts={noticeStates} /></Card></div></div></Section>
    <Section priority={2} title="Avisos operativos"><div className="dashboard-notice-band tw-grid tw-gap-3 lg:tw-grid-cols-[minmax(220px,0.32fr)_minmax(0,1fr)]"><Metric label="Avisos que requieren gestión" value={d.notices_open} note="Pendientes o en seguimiento" />{showAlerts && <Card className={cardStyle} title="Alertas operativas"><div className="tw-mb-3 tw-flex tw-gap-2"><button type="button" className="row-action" onClick={() => setAlertScope('all')}>Todas</button><button type="button" className="row-action" onClick={() => setAlertScope('mine')}>Asignadas a mí</button></div>{visibleAlerts.length ? visibleAlerts.map((item, index) => <div className="operational-alert" key={item.id || index}><Tag value={item.kind === 'DELAY' ? 'Demora' : item.kind === 'STANDARD_APPROVAL' ? 'Aprobación' : 'Revisión'} severity={item.severity === 'OVERDUE' ? 'danger' : 'warning'} /><strong>{item.title}</strong><small>{item.responsible} · {fmt(item.due_at)}</small></div>) : <div className="empty">No hay alertas operativas.</div>}</Card>}</div></Section>
    <Section priority={3} title="Programados pendientes"><div className="dashboard-programmed-band tw-grid tw-gap-3 lg:tw-grid-cols-[minmax(220px,0.32fr)_minmax(0,1fr)]"><Metric label="Programados pendientes" value={d.transfers_pending} note="Sin asignar, asignados o en curso" /><Card className={cardStyle} title="Estado de programados pendientes"><Bars counts={transferStates} /></Card></div></Section>
  </div>;
}
