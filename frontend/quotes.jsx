import React, { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Card } from 'primereact/card';
import { Checkbox } from 'primereact/checkbox';
import { Column } from 'primereact/column';
import { DataTable } from './dense-table.jsx';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { InputText } from 'primereact/inputtext';
import { SelectButton } from 'primereact/selectbutton';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';

const blank = { task_number: '', coverage: 'insured', special: false, gavilan: false, origin: '', destination: '', mobile_origin: '', manual_trip_km: null, manual_mobile_km: null, manual_toll_count: null, include_mobile: false, include_tolls: false };
const money = value => new Intl.NumberFormat('es-UY', { style: 'currency', currency: 'UYU', maximumFractionDigits: 2, useGrouping: false }).format(Number(value || 0));
const stamp = value => value ? new Date(value).toLocaleString('es-UY', { dateStyle: 'short', timeStyle: 'short' }) : '—';
const tollsOf = value => { try { return Array.isArray(value) ? value : JSON.parse(value || '[]'); } catch { return []; } };
const snapshotOf = value => { try { return value && typeof value === 'object' ? value : JSON.parse(value || '{}'); } catch { return {}; } };

function QuoteField({ label, children }) { return <label className="quote-field tw-flex tw-min-w-0 tw-flex-col tw-gap-1"><span>{label}</span>{children}</label>; }

function QuoteMap({ result, onMarkerMove }) {
  const host = useRef(null);
  const mapRef = useRef(null);
  const viewRef = useRef(null);
  const callbackRef = useRef(onMarkerMove);
  callbackRef.current = onMarkerMove;
  useEffect(() => {
    const L = window.L;
    if (!L || !host.current || !result?.route_segments?.length) return;
    const map = L.map(host.current, { scrollWheelZoom: true });
    mapRef.current = map;
    L.tileLayer('/api/tiles/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
    const bounds = [];
    for (const segment of result.route_segments) {
      const points = (segment.coordinates || []).map(([lon, lat]) => [lat, lon]);
      if (!points.length) continue;
      L.polyline(points, { color: segment.color || '#2878b5', weight: 6, opacity: .9 }).addTo(map);
      bounds.push(...points);
    }
    for (const toll of tollsOf(result.toll_details)) {
      if (!Number.isFinite(Number(toll.latitude)) || !Number.isFinite(Number(toll.longitude))) continue;
      L.marker([Number(toll.latitude), Number(toll.longitude)], { title: `Peaje: ${toll.name}` }).bindTooltip(`Peaje: ${toll.name} · ${money(toll.price)}`).addTo(map);
    }
    const transfer = result.route_segments.find(segment => String(segment.label || '').startsWith('Traslado:')) || result.route_segments.at(-1);
    const mobile = result.route_segments.find(segment => String(segment.label || '').startsWith('Salida de la grúa'));
    const transferPoints = (transfer?.coordinates || []).map(([lon, lat]) => [lat, lon]);
    const mobilePoints = (mobile?.coordinates || []).map(([lon, lat]) => [lat, lon]);
    const marker = (point, field, label) => { if (!point) return; const item = L.marker(point, { draggable: true, title: `Arrastrá para ajustar ${label}` }).bindTooltip(label).addTo(map); item.on('dragend', event => { const position = event.target.getLatLng(); viewRef.current = { center: map.getCenter(), zoom: map.getZoom() }; callbackRef.current?.(field, `${position.lat.toFixed(6)}, ${position.lng.toFixed(6)}`); }); };
    marker(mobilePoints[0], 'mobile_origin', 'Origen de grúa');
    marker(transferPoints[0], 'origin', 'Origen');
    marker(transferPoints.at(-1), 'destination', 'Destino');
    if (viewRef.current) map.setView(viewRef.current.center, viewRef.current.zoom);
    else if (bounds.length) map.fitBounds(bounds, { padding: [24, 24] });
    const resize = new ResizeObserver(() => map.invalidateSize({ pan: false }));
    resize.observe(host.current);
    const timer = setTimeout(() => map.invalidateSize(), 50);
    return () => { clearTimeout(timer); resize.disconnect(); viewRef.current = { center: map.getCenter(), zoom: map.getZoom() }; map.remove(); mapRef.current = null; };
  }, [result]);
  return <div className="quote-map-card"><div className="quote-map-head"><strong>Recorrido calculado</strong><span>{Number(result.total_km).toFixed(2)} km totales</span></div><div className="quote-map-resizer" style={{ resize: 'vertical', overflow: 'hidden', minHeight: 418 }}><div id="quote-map" ref={host} className="quote-map" aria-label="Mapa del recorrido" style={{ height: '100%', minHeight: 418 }} /></div><div className="route-legend">{result.route_segments.map((segment, index) => <span key={index}><i style={{ background: segment.color || '#2878b5' }} />{segment.label}</span>)}</div></div>;
}

function Result({ result, error, onManual, onCopy, onMarkerMove }) {
  if (error) return <Card className="quote-result-card"><div className="quote-placeholder quote-error"><strong>No se pudo calcular la cotización</strong><p>{error}</p><Button className="tw-h-9" label="Pasar a distancia manual" text onClick={onManual} /></div></Card>;
  if (!result) return <Card className="quote-result-card"><div className="quote-placeholder"><strong>Resultado de la cotización</strong><p>Elegí una modalidad y completá los datos para obtener el precio.</p></div></Card>;
  const tolls = tollsOf(result.toll_details);
  const lines = [['Traslado: origen → destino', `${Number(result.trip_km).toFixed(2)} km`], ['Salida de la grúa → origen', `${Number(result.mobile_km).toFixed(2)} km`], ['Distancia total considerada', `${Number(result.total_km).toFixed(2)} km`], ['Kilómetros incluidos', `${result.included_km} km`], ['Kilómetros excedentes', `${result.extra_km} km × ${money(result.extra_rate)}`], ['Precio base', money(result.base_price)], ['Adicional por km', money(result.extra_price)], [`Peajes (${Number(result.toll_count || tolls.length)})`, money(result.toll_price)], ['Total', money(result.total_price)]];
  return <Card className="quote-result-card tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><div className="quote-result-summary"><Tag value={`${result.customer_type} · ${result.mode === 'manual' ? 'Manual' : 'Automática'}`} />{result.task_number && <p>Tarea {result.task_number}</p>}<div className="quote-total-label">Precio a informar</div><div className="quote-total">{money(result.total_price)}</div><Button className="tw-h-9" label="Copiar resumen de cotización" icon="pi pi-copy" size="small" outlined onClick={onCopy} /></div>{result.route_segments?.length > 0 && <QuoteMap result={result} onMarkerMove={onMarkerMove} />}<div className="quote-breakdown">{lines.map(([label, value]) => <div className="quote-line" key={label}><span>{label}</span><strong>{value}</strong></div>)}{tolls.length > 0 && <div className="quote-toll-list">{tolls.map((toll, index) => <div key={index}><span>{toll.name} <small>{toll.segment}</small></span><strong>{money(toll.price)}</strong></div>)}</div>}</div><div className="quote-warning">Verificá el recorrido y el tipo de servicio antes de comunicar el precio.</div></Card>;
}

function draftFor(key) { try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch { return null; } }

export function QuoteView({ model }) {
  const initial = useRef(draftFor(model.draftKey));
  const [tab, setTab] = useState('new');
  const [mode, setMode] = useState(initial.current?.mode === 'manual' ? 'manual' : 'automatic');
  const [form, setForm] = useState({ ...blank, ...initial.current });
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [filters, setFilters] = useState({ search: '', coverage: '', mode: '' });
  const [applied, setApplied] = useState(filters);
  const toast = useRef(null);
  const notify = (severity, summary, detail) => toast.current?.show({ severity, summary, detail, life: severity === 'error' ? 5500 : 3200 });
  useEffect(() => { try { localStorage.setItem(model.draftKey, JSON.stringify({ ...form, mode })); } catch { /* El formulario sigue disponible durante la sesión. */ } }, [form, mode, model.draftKey]);
  useEffect(() => {
    if (tab !== 'history') return;
    let active = true;
    const query = new URLSearchParams({ limit: '50', offset: String(page * 50) });
    if (applied.search) query.set('q', applied.search);
    if (applied.coverage) query.set('coverage', applied.coverage);
    if (applied.mode) query.set('mode', applied.mode);
    model.request(`/api/quotes/history?${query}`).then(response => { if (active) { setHistory(response.items || []); setTotal(Number(response.total || 0)); } }).catch(failure => { if (active) notify('error', 'No se pudo cargar el historial', failure.message); });
    return () => { active = false; };
  }, [tab, page, applied, model.request]);
  const update = (name, value) => { setForm(current => ({ ...current, [name]: value })); setResult(null); setError(''); };
  const switchMode = value => { setMode(value); setResult(null); setError(''); };
  const calculate = async (values = form) => {
    if (busy) return;
    const manual = mode === 'manual';
    if (manual && (!values.manual_trip_km || (values.include_mobile && !values.manual_mobile_km))) { setError('Completá las distancias del servicio.'); return; }
    if (!manual && (!values.origin?.trim() || !values.destination?.trim() || (values.include_mobile && !values.mobile_origin?.trim()))) { setError('Completá las ubicaciones del recorrido.'); return; }
    if (manual && values.include_tolls && !values.manual_toll_count) { setError('Indicá la cantidad de peajes.'); return; }
    const body = { task_number: values.task_number || null, origin: manual ? null : values.origin, destination: manual ? null : values.destination, mobile_origin: !manual && values.include_mobile ? values.mobile_origin : null, manual_trip_km: manual ? Number(values.manual_trip_km) : null, manual_mobile_km: manual && values.include_mobile ? Number(values.manual_mobile_km) : 0, include_mobile: Boolean(values.include_mobile), include_tolls: manual && Boolean(values.include_tolls), manual_toll_count: manual && values.include_tolls ? Number(values.manual_toll_count) : null, uninsured: values.coverage === 'uninsured', special: Boolean(values.special), gavilan: Boolean(values.gavilan), manual_distance: manual };
    setBusy(true);
    try { const response = await model.request('/api/quotes/calculate', { method: 'POST', body: JSON.stringify(body) }); setResult({ ...response, _input: body }); setError(''); notify('success', 'Cotización guardada en el historial'); window.toast?.('Cotización guardada en el historial'); }
    catch (failure) { setResult(null); setError(failure.message || 'No se pudo calcular la cotización'); notify('error', 'No se pudo calcular', failure.message); }
    finally { setBusy(false); }
  };
  const recover = row => { const manual = row.origin_input === 'Cotización manual', pricing = snapshotOf(row.pricing_snapshot); setMode(manual ? 'manual' : 'automatic'); setForm({ ...blank, task_number: row.task_number || '', origin: manual ? '' : row.origin_input || '', destination: manual ? '' : row.destination_input || '', mobile_origin: row.mobile_input || '', manual_trip_km: Number(row.trip_km), manual_mobile_km: Number(row.mobile_km), manual_toll_count: manual && Number(row.toll_count) > 0 ? Number(row.toll_count) : null, include_mobile: Number(row.mobile_km) > 0, include_tolls: manual && Number(row.toll_count) > 0, coverage: row.uninsured ? 'uninsured' : 'insured', special: Boolean(row.special), gavilan: Boolean(row.gavilan) }); setResult({ ...row, mode: manual ? 'manual' : 'automatic', extra_rate: Number(pricing.extra_rate ?? (Number(row.extra_km) ? Number(row.extra_price) / Number(row.extra_km) : 0)), route_segments: [], customer_type: `${row.uninsured ? 'No asegurado' : 'Asegurado'}${row.gavilan ? ' · Gavilán' : row.special ? ' · Especial' : ''}` }); setTab('new'); notify('success', 'Cotización recuperada'); };
  const copy = async () => { if (!result) return; const text = [`COTIZACIÓN DE SERVICIO`, result.task_number && `Tarea: ${result.task_number}`, `Tipo: ${result.customer_type}`, `Modalidad: ${result.mode === 'manual' ? 'Manual' : 'Automática'}`, `Distancia total: ${Number(result.total_km).toFixed(2)} km`, `Peajes: ${result.toll_count || 0}`, `PRECIO A INFORMAR: ${money(result.total_price)}`].filter(Boolean).join('\n'); try { await navigator.clipboard.writeText(text); notify('success', 'Resumen copiado'); } catch (failure) { notify('error', 'No se pudo copiar', failure.message); } };
  const markerMove = (name, value) => { const next = { ...form, [name]: value }; setForm(next); calculate(next); };
  const tabOptions = [{ label: 'Nueva cotización', value: 'new' }, { label: 'Historial', value: 'history' }];
  return <div className="operational-view quote-prime-view tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]"><Toast ref={toast} /><SelectButton value={tab} options={tabOptions} optionLabel="label" optionValue="value" allowEmpty={false} onChange={event => event.value && setTab(event.value)} />
    {tab === 'history' ? <><Card className="tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-2"><strong>Historial paginado · {total} cotizaciones</strong>{model.canExport && <Button className="tw-h-9" label="Descargar esta vista" outlined size="small" onClick={() => model.onExport(applied)} />}</div><div className="tw-mt-3 tw-flex tw-flex-wrap tw-items-end tw-gap-4"><QuoteField label="Buscar tarea, origen, destino o usuario"><InputText className="tw-h-9" value={filters.search} onChange={event => setFilters(current => ({ ...current, search: event.target.value }))} onKeyDown={event => event.key === 'Enter' && (setPage(0), setApplied({ ...filters }))} /></QuoteField><QuoteField label="Cobertura"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.coverage} options={[{ label: 'Todas', value: '' }, { label: 'Asegurado', value: 'insured' }, { label: 'No asegurado', value: 'uninsured' }]} onChange={event => setFilters(current => ({ ...current, coverage: event.value }))} /></QuoteField><QuoteField label="Modalidad"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.mode} options={[{ label: 'Todas', value: '' }, { label: 'Manual', value: 'manual' }, { label: 'Automática', value: 'automatic' }]} onChange={event => setFilters(current => ({ ...current, mode: event.value }))} /></QuoteField><Button className="tw-h-9" label="Aplicar filtros" size="small" onClick={() => { setPage(0); setApplied({ ...filters }); }} /></div></Card><Card className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-0' }, content: { className: 'tw-p-0' } }}><DataTable stripedRows value={history} dataKey="id" size="small" scrollable emptyMessage="No hay cotizaciones para esos filtros"><Column header="Fecha" body={row => stamp(row.created_at)} /><Column header="Tarea" body={row => row.task_number || '—'} /><Column field="created_by" header="Usuario" /><Column header="Tipo" body={row => `${row.uninsured ? 'No asegurado' : 'Asegurado'}${row.gavilan ? ' · Gavilán' : row.special ? ' · Especial' : ''}`} /><Column header="Modalidad" body={row => row.origin_input === 'Cotización manual' ? 'Manual' : 'Automática'} /><Column header="Distancia" body={row => `${Number(row.total_km).toFixed(1)} km`} /><Column header="Peajes" body={row => `${row.toll_count || 0} · ${money(row.toll_price)}`} /><Column header="Total" body={row => money(row.total_price)} /><Column header="Acción" body={row => <Button className="tw-h-9" label="Recuperar" icon="pi pi-replay" text size="small" onClick={() => recover(row)} />} /></DataTable></Card><div className="tw-flex tw-items-center tw-justify-end tw-gap-2"><Button className="tw-h-9" label="Anterior" text disabled={page === 0} onClick={() => setPage(page - 1)} /><span>Página {page + 1}</span><Button className="tw-h-9" label="Siguiente" text disabled={(page + 1) * 50 >= total} onClick={() => setPage(page + 1)} /></div></> : <><div className="draft-notice"><span>La carga se guarda automáticamente como borrador en este equipo.</span><Button className="tw-h-9" label="Descartar borrador" text size="small" onClick={() => { setForm(blank); setResult(null); setError(''); try { localStorage.removeItem(model.draftKey); } catch { /* Sin almacenamiento local. */ } }} /></div><SelectButton value={mode} options={[{ label: 'Automática por ubicaciones', value: 'automatic' }, { label: 'Manual por kilómetros', value: 'manual' }]} optionLabel="label" optionValue="value" allowEmpty={false} onChange={event => event.value && switchMode(event.value)} /><div className="quote-prime-layout tw-grid tw-min-w-0 tw-gap-3 xl:tw-grid-cols-[minmax(0,1fr)_minmax(320px,0.55fr)]"><form className="quote-form-panel tw-flex tw-min-w-0 tw-flex-col tw-gap-4" onSubmit={event => { event.preventDefault(); calculate(); }}><Card className="quote-step-card tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" title="1 · Identificación"><QuoteField label="Número de tarea (opcional)"><InputText className="tw-h-9" value={form.task_number} onChange={event => update('task_number', event.target.value)} placeholder="Ej.: 123456" maxLength={120} /></QuoteField></Card><Card className="quote-step-card tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" title="2 · Cobertura y vehículo"><div className="tw-grid tw-gap-3"><QuoteField label="Cobertura"><Dropdown appendTo={document.body} className="tw-h-9" value={form.coverage} options={[{ label: 'Asegurado', value: 'insured' }, { label: 'No asegurado', value: 'uninsured' }]} onChange={event => update('coverage', event.value)} /></QuoteField><label className="tw-flex tw-items-center tw-gap-2"><Checkbox checked={Boolean(form.special)} onChange={event => { setForm(current => ({ ...current, special: event.checked, gavilan: false })); setResult(null); }} />Especial</label><label className="tw-flex tw-items-center tw-gap-2"><Checkbox checked={Boolean(form.gavilan)} onChange={event => { setForm(current => ({ ...current, gavilan: event.checked, special: false })); setResult(null); }} />Gavilán</label></div></Card><Card className="quote-step-card tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" title={mode === 'manual' ? '3 · Distancias del servicio' : '3 · Ubicaciones del servicio'}><div className="tw-grid tw-gap-3">{mode === 'automatic' ? <><QuoteField label="Origen del cliente"><InputText className="tw-h-9" value={form.origin} onChange={event => update('origin', event.target.value)} required placeholder="Coordenadas o enlace de Google Maps" /></QuoteField><QuoteField label="Destino del traslado"><InputText className="tw-h-9" value={form.destination} onChange={event => update('destination', event.target.value)} required placeholder="Coordenadas o enlace de Google Maps" /></QuoteField></> : <QuoteField label="Traslado: origen → destino (km)"><InputNumber value={form.manual_trip_km} onValueChange={event => update('manual_trip_km', event.value)} min={0.1} maxFractionDigits={1} locale="es-UY" useGrouping={false} /></QuoteField>}<label className="tw-flex tw-items-center tw-gap-2"><Checkbox checked={Boolean(form.include_mobile)} onChange={event => update('include_mobile', event.checked)} />Incluir salida de la grúa</label>{form.include_mobile && (mode === 'automatic' ? <QuoteField label="Ubicación de salida de la grúa"><InputText className="tw-h-9" value={form.mobile_origin} onChange={event => update('mobile_origin', event.target.value)} required /></QuoteField> : <QuoteField label="Salida de la grúa → origen (km)"><InputNumber value={form.manual_mobile_km} onValueChange={event => update('manual_mobile_km', event.value)} min={0.1} maxFractionDigits={1} locale="es-UY" useGrouping={false} /></QuoteField>)}{mode === 'manual' && <><label className="tw-flex tw-items-center tw-gap-2"><Checkbox checked={Boolean(form.include_tolls)} onChange={event => update('include_tolls', event.checked)} />Incluir peajes</label>{form.include_tolls && <QuoteField label="Cantidad de peajes"><InputNumber value={form.manual_toll_count} onValueChange={event => update('manual_toll_count', event.value)} min={1} max={100} useGrouping={false} /></QuoteField>}</>}</div></Card><Button className="tw-h-9" type="submit" label={busy ? 'Calculando…' : mode === 'manual' ? 'Calcular cotización manual' : 'Trazar recorrido y calcular'} loading={busy} disabled={busy || !model.canCreate} /></form><Result result={result} error={error} onManual={() => switchMode('manual')} onCopy={copy} onMarkerMove={markerMove} /></div></>}
  </div>;
}
