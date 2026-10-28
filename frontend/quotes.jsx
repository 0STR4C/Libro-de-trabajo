import React, { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Card } from 'primereact/card';
import { Checkbox } from 'primereact/checkbox';
import { Column } from 'primereact/column';
import { DataTable } from './dense-table.jsx';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { InputText } from 'primereact/inputtext';
import { ProgressSpinner } from 'primereact/progressspinner';
import { SelectButton } from 'primereact/selectbutton';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { formatDateTime } from './date-format.js';
import { createQuoteRequestGuard } from './quote-request-guard.js';
import { blank, normalizeQuoteDraft } from './quote-draft.js';
import { formatUYU } from './money.js';
import { isDirectLocation, manualRegionPoints, regionalSelection, selectedCoordinates } from './quote-address.js';

const money = formatUYU;
const stamp = formatDateTime;
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
    marker(transferPoints[0], 'origin', '1 · Origen del servicio');
    marker(transferPoints.at(-1), 'destination', '2 · Destino del servicio');
    marker(mobilePoints[0], 'mobile_origin', '3 · Salida de la grúa');
    if (viewRef.current) map.setView(viewRef.current.center, viewRef.current.zoom);
    else if (bounds.length) map.fitBounds(bounds, { padding: [24, 24] });
    const resize = new ResizeObserver(() => map.invalidateSize({ pan: false }));
    resize.observe(host.current);
    const timer = setTimeout(() => map.invalidateSize(), 50);
    return () => { clearTimeout(timer); resize.disconnect(); viewRef.current = { center: map.getCenter(), zoom: map.getZoom() }; map.remove(); mapRef.current = null; };
  }, [result]);
  return <div className="quote-map-card"><div className="quote-map-head"><strong>Recorrido calculado</strong><span>{Number(result.total_km).toFixed(2)} km totales</span></div><div className="quote-map-resizer" style={{ resize: 'vertical', overflow: 'hidden', minHeight: 360, height: 400 }}><div id="quote-map" ref={host} className="quote-map" aria-label="Mapa del recorrido" style={{ height: '100%', minHeight: 360 }} /></div><div className="route-legend">{result.route_segments.map((segment, index) => <span key={index}><i style={{ background: segment.color || '#2878b5' }} />{segment.label}</span>)}</div></div>;
}

function Result({ result, error, uncertain, onManual, onCopy, onMarkerMove }) {
  if (error) return <Card className="quote-result-card"><div className="quote-placeholder quote-error"><strong>{uncertain ? 'Guardado sin confirmar' : 'Cotización no guardada'}</strong><p>{error}</p>{!uncertain && /motor de rutas/i.test(error) && <Button className="tw-h-9" label="Pasar a distancia manual" text onClick={onManual} />}</div></Card>;
  if (!result) return <Card className="quote-result-card"><div className="quote-placeholder"><strong>Resultado de la cotización</strong><p>Elegí una modalidad y completá los datos para obtener el precio.</p></div></Card>;
  const tolls = tollsOf(result.toll_details);
  const lines = [['Traslado: origen → destino', `${Number(result.trip_km).toFixed(2)} km`], ['Salida de la grúa → origen', `${Number(result.mobile_km).toFixed(2)} km`], ['Distancia total considerada', `${Number(result.total_km).toFixed(2)} km`], ['Kilómetros incluidos', `${result.included_km} km`], ['Kilómetros excedentes', `${result.extra_km} km × ${money(result.extra_rate)}`], ['Precio base', money(result.base_price)], ['Adicional por km', money(result.extra_price)], [`Peajes (${Number(result.toll_count || tolls.length)})`, money(result.toll_price)], ['Total', money(result.total_price, { cents: true })]];
  return <Card className="quote-result-card tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><div className="quote-result-summary"><Tag value={`${result.customer_type} · ${result.mode === 'manual' ? 'Manual' : 'Automática'}`} />{result.task_number && <p>Tarea {result.task_number}</p>}<div className="quote-total-label">Precio a informar</div><div className="quote-total">{money(result.total_price, { cents: true })}</div><Button className="tw-h-9" label="Copiar resumen de cotización" icon="pi pi-copy" size="small" outlined onClick={onCopy} /></div><QuoteBreakdown lines={lines} tolls={tolls} />{result.route_segments?.length > 0 && <QuoteMap result={result} onMarkerMove={onMarkerMove} />}<div className="quote-warning">Verificá el recorrido y el tipo de servicio antes de comunicar el precio.</div></Card>;
}

function QuoteBreakdown({ lines, tolls }) {
  return <div className="tw-grid tw-min-w-0 tw-gap-2 2xl:tw-grid-cols-2">
    {[['Kilómetros calculados',lines.slice(0,5)],['Ítems cotizados',lines.slice(5)]].map(([title,items])=><div key={title} className="tw-rounded-md tw-border tw-border-slate-200 tw-p-3"><strong className="tw-block tw-mb-2">{title}</strong>{items.map(([label,value])=><div className="quote-line" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>)}
    {tolls.length>0&&<div className="tw-rounded-md tw-border tw-border-slate-200 tw-p-3"><strong className="tw-block tw-mb-2">Detalle de peajes</strong>{tolls.map((toll,index)=><div className="quote-line" key={index}><span>{toll.name} <small>{toll.segment}</small></span><strong>{money(toll.price)}</strong></div>)}</div>}
  </div>;
}

function draftFor(key) { try { return normalizeQuoteDraft(JSON.parse(localStorage.getItem(key) || 'null')); } catch { return null; } }

function PointPreview({ point, onMove }) {
  const host = useRef(null);
  useEffect(() => {
    const L = window.L;
    if (!L || !host.current) return;
    const map = L.map(host.current, { scrollWheelZoom: true }).setView([point.latitude, point.longitude], 14);
    L.tileLayer('/api/tiles/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
    const marker = L.marker([point.latitude, point.longitude], { draggable: true, title: 'Arrastrá para ajustar el punto' }).addTo(map);
    marker.on('dragend', () => { const next = marker.getLatLng(); onMove({ latitude: next.lat, longitude: next.lng }); });
    const timer = setTimeout(() => map.invalidateSize(), 30);
    return () => { clearTimeout(timer); map.remove(); };
  }, [point.latitude, point.longitude]);
  return <div ref={host} role="img" aria-label="Punto interpretado en el mapa; arrastrá el marcador para ajustarlo" className="tw-w-full tw-rounded-md" style={{ height: 200 }} />;
}

function AddressField({ label, field, value, mode, country, confirmed, onChange, onSelect, onMode }) {
  const [suggestions, setSuggestions] = useState([]);
  const [state, setState] = useState('');
  const [selected, setSelected] = useState(null);
  const [preview, setPreview] = useState(null);
  const [checking, setChecking] = useState(false);
  const verification = useRef(0);
  useEffect(() => () => { verification.current += 1; }, [value, mode, country]);
  useEffect(() => {
    if (selected && value !== selectedCoordinates(selected)) setSelected(null);
    if (mode !== 'address' || confirmed || !value?.trim() || isDirectLocation(value)) { setSuggestions([]); setState(''); return; }
    if (value.trim().length < 4) { setSuggestions([]); setState('Escribí al menos cuatro caracteres.'); return; }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setState('Buscando direcciones…');
      try {
        const response = await fetch(`/api/quotes/geocode?q=${encodeURIComponent(value.trim())}&country=${country}`, { credentials: 'same-origin', signal: controller.signal });
        const data = await response.json();
        if (controller.signal.aborted) return;
        if (!response.ok) throw new Error(data.detail || 'El servicio no respondió.');
        setSuggestions(data);
        setState(data.length ? 'Elegí una dirección de la lista para confirmar el punto.' : 'Sin resultados. Agregá ciudad, departamento o una referencia.');
      } catch (error) {
        if (error.name !== 'AbortError') { setSuggestions([]); setState(/GEOCODER_URL|configurar/i.test(error.message) ? 'Falta configurar la búsqueda de direcciones. Usá coordenadas o un enlace.' : 'El proveedor de direcciones no está disponible. Probá más tarde o usá coordenadas.'); }
      }
    }, 450);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [value, mode, country, confirmed]);
  const verify = async () => {
    const ticket = ++verification.current;
    setChecking(true); setPreview(null); setState('');
    try {
      const response = await fetch(`/api/quotes/resolve-location?q=${encodeURIComponent(value.trim())}`, { credentials: 'same-origin' });
      const data = await response.json();
      if (ticket !== verification.current) return;
      if (!response.ok) throw new Error(data.detail || 'No se pudo interpretar la ubicación.');
      setPreview(data);
      setState(data.inside_uruguay ? 'Revisá el pin en el mapa y confirmá el punto.' : 'Punto fuera del territorio tarifado o en agua. Ajustá el pin sobre una vía uruguaya si corresponde.');
    } catch (error) { if (ticket === verification.current) setState(error.message); }
    finally { if (ticket === verification.current) setChecking(false); }
  };
  const change = text => { verification.current += 1; setPreview(null); setSelected(null); onChange(field, text); };
  return <div className="tw-grid tw-min-w-0 tw-gap-1">
    <strong>{label}</strong>
    <SelectButton value={mode} options={[{ label: 'Buscar dirección', value: 'address' }, { label: 'Coordenadas o enlace', value: 'coordinates' }]} optionLabel="label" optionValue="value" allowEmpty={false} onChange={event => { if (event.value) { verification.current += 1; setPreview(null); setSelected(null); onMode(field, event.value); } }} />
    {mode === 'address' && <label className="tw-grid tw-gap-1">País<Dropdown appendTo={document.body} value={country} options={[{ label: 'Uruguay', value: 'UY' }, { label: 'Argentina', value: 'AR' }, { label: 'Brasil', value: 'BR' }]} onChange={event => { setSelected(null); setPreview(null); onChange(`${field}_country`, event.value); onChange(field, ''); }} /></label>}
    <label htmlFor={`quote-${field}`}>{mode === 'address' ? 'Calle, número, esquina o referencia; ciudad opcional' : 'Latitud, longitud o enlace de ubicación'}</label>
    <InputText id={`quote-${field}`} aria-label={label} className="tw-h-9 tw-w-full tw-min-w-0" value={value} onChange={event => change(event.target.value)} placeholder={mode === 'address' ? 'Ej.: 18 de Julio y Ejido, Montevideo' : '-34.901100, -56.164500 o enlace de Maps'} autoComplete="off" />
    {confirmed && <small className="tw-text-green-700 dark:tw-text-green-300">{selected?.label ? `${selected.label} · ` : ''}Punto confirmado</small>}
    {state && <small role="status" className="tw-text-slate-600 dark:tw-text-slate-300">{state}</small>}
    {mode === 'coordinates' && !confirmed && <Button type="button" label={checking ? 'Interpretando…' : 'Ver punto en el mapa'} loading={checking} disabled={!value.trim() || checking} outlined size="small" onClick={verify} />}
    {mode === 'coordinates' && preview && !confirmed && <><PointPreview point={preview} onMove={point => { setPreview(point); setState('Punto ajustado. Confirmá el pin o movelo de nuevo.'); }} /><Button type="button" label="Confirmar este punto" size="small" onClick={() => { onSelect(field, { ...preview, country_code: preview.inside_uruguay ? 'UY' : '' }); setPreview(null); setState(''); }} /></>}
    {mode === 'address' && suggestions.length > 0 && <ul role="listbox" aria-label={`Sugerencias para ${label}`} className="tw-grid tw-min-w-0 tw-gap-1 tw-rounded-md tw-border tw-border-slate-300 tw-p-1 dark:tw-border-slate-600">
      {suggestions.map((item, index) => <li key={`${item.country_code}-${item.latitude}-${item.longitude}-${index}`}><button type="button" role="option" aria-selected="false" className="tw-w-full tw-min-w-0 tw-rounded tw-p-2 tw-text-left tw-text-[13px] hover:tw-bg-slate-100 dark:hover:tw-bg-slate-700" onClick={() => { setSelected(item); setSuggestions([]); setState(''); onSelect(field, item); }}>{item.label}<small className="tw-block tw-text-slate-500 dark:tw-text-slate-300">{Number(item.latitude).toFixed(5)}, {Number(item.longitude).toFixed(5)}</small></button></li>)}
    </ul>}
  </div>;
}

function TripFields({ mode, form, update, selectPoint, changeLocationMode }) {
  const automatic = mode === 'automatic';
  const point = (field, label) => <AddressField label={label} field={field} value={form[field]} mode={form[`${field}_entry_mode`]} country={form[`${field}_country`]} confirmed={form[`${field}_confirmed`]} onChange={update} onSelect={selectPoint} onMode={changeLocationMode} />;
  return <div className="tw-grid tw-gap-2">
    <div className="tw-rounded-md tw-border tw-border-slate-200 tw-p-3">
      <strong className="tw-block tw-mb-2">1 · Origen del servicio</strong>
      {point('origin', `Punto de recogida${automatic ? '' : ' (opcional)'}`)}
    </div>
    <div className="tw-rounded-md tw-border tw-border-slate-200 tw-p-3">
      <strong className="tw-block tw-mb-2">2 · Destino del servicio</strong>
      {point('destination', `Punto de entrega${automatic ? '' : ' (opcional)'}`)}
      {!automatic && <QuoteField label="Origen → destino (km)"><InputNumber value={form.manual_trip_km} onValueChange={event => update('manual_trip_km', event.value)} min={0.1} maxFractionDigits={1} locale="es-UY" useGrouping={false} /></QuoteField>}
    </div>
    <div className="tw-rounded-md tw-border tw-border-slate-200 tw-p-3">
      <strong className="tw-block tw-mb-2">3 · Salida de la grúa</strong>
      <label className="tw-flex tw-items-center tw-gap-2"><Checkbox checked={Boolean(form.include_mobile)} onChange={event => update('include_mobile', event.checked)} />Incluir desplazamiento desde la base</label>
      {form.include_mobile && point('mobile_origin', `Ubicación de la base${automatic ? '' : ' (opcional)'}`)}
      {form.include_mobile && !automatic && <QuoteField label="Base → origen (km)"><InputNumber value={form.manual_mobile_km} onValueChange={event => update('manual_mobile_km', event.value)} min={0.1} maxFractionDigits={1} locale="es-UY" useGrouping={false} /></QuoteField>}
      {!form.include_mobile && <small className="tw-text-slate-500">Sin kilómetros desde la base.</small>}
    </div>
    {mode === 'manual' && <div className="tw-rounded-md tw-border tw-border-slate-200 tw-p-3"><label className="tw-flex tw-items-center tw-gap-2"><Checkbox checked={Boolean(form.include_tolls)} onChange={event => update('include_tolls', event.checked)} />Incluir peajes</label>{form.include_tolls && <QuoteField label="Cantidad de peajes"><InputNumber value={form.manual_toll_count} onValueChange={event => update('manual_toll_count', event.value)} min={1} max={100} useGrouping={false} /></QuoteField>}</div>}
  </div>;
}

export function QuoteView({ model }) {
  const initial = useRef(draftFor(model.draftKey));
  const [tab, setTab] = useState(model.tab === 'history' ? 'history' : 'new');
  useEffect(() => { setTab(model.tab === 'history' ? 'history' : 'new'); }, [model.tab]);
  const [mode, setMode] = useState(initial.current?.mode === 'manual' ? 'manual' : 'automatic');
  const [form, setForm] = useState({ ...blank, ...initial.current });
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);
  const [historyLoading,setHistoryLoading]=useState(false);
  const [filters, setFilters] = useState({ search: '', coverage: '', mode: '' });
  const [applied, setApplied] = useState(filters);
  const toast = useRef(null);
  const requestGuard = useRef(createQuoteRequestGuard());
  const [confirmationUnknown, setConfirmationUnknown] = useState(false);
  useEffect(() => () => { requestGuard.current.invalidate(); }, []);
  const notify = (severity, summary, detail) => toast.current?.show({ severity, summary, detail, life: severity === 'error' ? 5500 : 3200 });
  useEffect(() => { try { localStorage.setItem(model.draftKey, JSON.stringify({ ...form, mode })); } catch { /* El formulario sigue disponible durante la sesión. */ } }, [form, mode, model.draftKey]);
  useEffect(() => {
    if (tab !== 'history') return;
    let active = true;
    setHistoryLoading(true);
    const query = new URLSearchParams();
    if (applied.search) query.set('q', applied.search);
    if (applied.coverage) query.set('coverage', applied.coverage);
    if (applied.mode) query.set('mode', applied.mode);
    model.request(`/api/quotes/history?${query}`).then(response => { if (active) setHistory(response || []); }).catch(failure => { if (active) notify('error', 'No se pudo cargar el historial', failure.message); }).finally(()=>{if(active)setHistoryLoading(false);});
    return () => { active = false; };
  }, [tab, applied, model.request]);
  const invalidate = () => { requestGuard.current.invalidate(); setResult(null); setError(''); setConfirmationUnknown(false); };
  const update = (name, value) => { invalidate(); setForm(current => ({ ...current, [name]: value, ...(['origin', 'destination', 'mobile_origin'].includes(name) ? { [`${name}_confirmed`]: false } : {}) })); };
  const selectPoint = (name, item) => { invalidate(); setForm(current => ({ ...current, [name]: selectedCoordinates(item), [`${name}_country`]: item.country_code || '', [`${name}_confirmed`]: true })); };
  const changeLocationMode = (name, value) => { invalidate(); setForm(current => ({ ...current, [name]: '', [`${name}_entry_mode`]: value, [`${name}_confirmed`]: false })); };
  const switchMode = value => { invalidate(); setMode(value); };
  const calculate = async (values = form) => {
    if (requestGuard.current.pending) return;
    const manual = mode === 'manual';
    if (regionalSelection(values)) { setError('El recorrido incluye una ubicación fuera de Uruguay. No hay tarifa regional configurada: requiere cálculo manual externo o una tarifa aprobada.'); return; }
    if (manual && (!values.manual_trip_km || (values.include_mobile && !values.manual_mobile_km))) { setError('Completá las distancias del servicio.'); return; }
    if (manual && ['origin', 'destination', ...(values.include_mobile ? ['mobile_origin'] : [])].some(name => values[name]?.trim() && (!values[`${name}_confirmed`] || !isDirectLocation(values[name])))) { setError('Confirmá cada ubicación ingresada, o dejala vacía si solo conocés los kilómetros.'); return; }
    if (!manual && (!values.origin?.trim() || !values.destination?.trim() || (values.include_mobile && !values.mobile_origin?.trim()))) { setError('Completá las ubicaciones del recorrido.'); return; }
    if (!manual && ['origin', 'destination', ...(values.include_mobile ? ['mobile_origin'] : [])].some(name => !values[`${name}_confirmed`] || !isDirectLocation(values[name]))) { setError('Confirmá cada punto: elegí una sugerencia o verificá las coordenadas en el mapa.'); return; }
    if (manual && values.include_tolls && !values.manual_toll_count) { setError('Indicá la cantidad de peajes.'); return; }
    const body = { task_number: values.task_number || null, origin: manual ? null : values.origin, destination: manual ? null : values.destination, mobile_origin: !manual && values.include_mobile ? values.mobile_origin : null, manual_trip_km: manual ? Number(values.manual_trip_km) : null, manual_mobile_km: manual && values.include_mobile ? Number(values.manual_mobile_km) : 0, manual_region_points: manual ? manualRegionPoints(values) : [], include_mobile: Boolean(values.include_mobile), include_tolls: manual && Boolean(values.include_tolls), manual_toll_count: manual && values.include_tolls ? Number(values.manual_toll_count) : null, uninsured: values.coverage === 'uninsured', special: Boolean(values.special), gavilan: Boolean(values.gavilan), manual_distance: manual };
    const fingerprint = JSON.stringify(body);
    if (requestGuard.current.submitted === fingerprint) {
      notify('warn', 'Cotización ya enviada', 'Para crear otra cotización idéntica, elegí Nueva cotización explícitamente.');
      return;
    }
    const { revision: sequence } = requestGuard.current.begin(fingerprint);
    setConfirmationUnknown(false);
    setBusy(true);
    try { const response = await model.request('/api/quotes/calculate', { method: 'POST', body: JSON.stringify(body) }); if(!requestGuard.current.isCurrent(sequence))return; setResult({ ...response, _input: body }); setError(''); notify('success', 'Cotización guardada en el historial'); window.toast?.('Cotización guardada en el historial'); }
    catch (failure) { if(!requestGuard.current.isCurrent(sequence)||failure.stale)return; setResult(null); const uncertain = !failure.status || failure.status >= 500; if (!uncertain) requestGuard.current.rejectKnown(); setConfirmationUnknown(uncertain); setError(uncertain ? 'No se confirmó la respuesta. La cotización podría estar guardada: revisá el historial antes de iniciar otra.' : failure.message || 'No se pudo calcular la cotización'); notify('error', uncertain ? 'No se pudo confirmar la cotización' : 'Cotización rechazada antes de guardar', failure.message); }
    finally { requestGuard.current.finish(); setBusy(false); }
  };
  const recover = row => { invalidate(); requestGuard.current.allowNew(); const manual = row.origin_input === 'Cotización manual', pricing = snapshotOf(row.pricing_snapshot); setMode(manual ? 'manual' : 'automatic'); setForm({ ...blank, task_number: row.task_number || '', origin: manual ? '' : row.origin_input || '', destination: manual ? '' : row.destination_input || '', mobile_origin: row.mobile_input || '', origin_entry_mode: 'coordinates', destination_entry_mode: 'coordinates', mobile_origin_entry_mode: 'coordinates', origin_confirmed: !manual && isDirectLocation(row.origin_input), destination_confirmed: !manual && isDirectLocation(row.destination_input), mobile_origin_confirmed: Boolean(row.mobile_input && isDirectLocation(row.mobile_input)), manual_trip_km: Number(row.trip_km), manual_mobile_km: Number(row.mobile_km), manual_toll_count: manual && Number(row.toll_count) > 0 ? Number(row.toll_count) : null, include_mobile: Number(row.mobile_km) > 0, include_tolls: manual && Number(row.toll_count) > 0, coverage: row.uninsured ? 'uninsured' : 'insured', special: Boolean(row.special), gavilan: Boolean(row.gavilan) }); setResult({ ...row, mode: manual ? 'manual' : 'automatic', extra_rate: Number(pricing.extra_rate ?? (Number(row.extra_km) ? Number(row.extra_price) / Number(row.extra_km) : 0)), route_segments: [], customer_type: `${row.uninsured ? 'No asegurado' : 'Asegurado'}${row.gavilan ? ' · Gavilán' : row.special ? ' · Especial' : ''}` }); setTab('new'); notify('success', 'Cotización recuperada'); };
  const copy = async () => {
    if (!result) return;
    const text = [
      'COTIZACIÓN DE SERVICIO',
      result.task_number && `Tarea: ${result.task_number}`,
      `Tipo: ${result.customer_type}`,
      `Modalidad: ${result.mode === 'manual' ? 'Manual' : 'Automática'}`,
      result.mode === 'automatic' && `1. Origen: ${result.origin_input}`,
      result.mode === 'automatic' && `2. Destino: ${result.destination_input}`,
      result.mode === 'automatic' && result.mobile_input && `3. Salida de la grúa: ${result.mobile_input}`,
      `Origen → destino: ${Number(result.trip_km).toFixed(2)} km`,
      `Base → origen: ${Number(result.mobile_km).toFixed(2)} km`,
      `Distancia total: ${Number(result.total_km).toFixed(2)} km`,
      `Peajes: ${result.toll_count || 0} · ${money(result.toll_price)}`,
      `PRECIO A INFORMAR: ${money(result.total_price, { cents: true })}`,
    ].filter(Boolean).join('\n');
    try { await navigator.clipboard.writeText(text); notify('success', 'Resumen copiado'); }
    catch (failure) { notify('error', 'No se pudo copiar', failure.message); }
  };
  const markerMove = (name, value) => { if (form[name] === value) return; const wasPending = requestGuard.current.pending; invalidate(); const next = { ...form, [name]: value, [`${name}_country`]: '', [`${name}_entry_mode`]: 'coordinates', [`${name}_confirmed`]: true }; setForm(next); if (!wasPending) calculate(next); };
  const startNew = () => { invalidate(); requestGuard.current.allowNew(); };
  const tabOptions = [{ label: 'Nueva cotización', value: 'new' }, { label: 'Historial', value: 'history' }];
  return <div className="operational-view quote-prime-view tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]"><Toast ref={toast} /><SelectButton value={tab} options={tabOptions} optionLabel="label" optionValue="value" allowEmpty={false} onChange={event => {if(event.value){setHistoryLoading(event.value === 'history');setTab(event.value);model.onTab?.(event.value);}}} />
    {tab === 'history' ? <><Card className="tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-2"><strong>Historial · {history.length} cotizaciones</strong>{model.canExport && <Button className="tw-h-9" label="Descargar esta vista" outlined size="small" onClick={() => model.onExport(applied)} />}</div><div className="tw-mt-3 tw-flex tw-flex-wrap tw-items-end tw-gap-4"><QuoteField label="Buscar tarea, origen, destino o usuario"><InputText className="tw-h-9" value={filters.search} onChange={event => setFilters(current => ({ ...current, search: event.target.value }))} onKeyDown={event => event.key === 'Enter' && setApplied({ ...filters })} /></QuoteField><QuoteField label="Cobertura"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.coverage} options={[{ label: 'Todas', value: '' }, { label: 'Asegurado', value: 'insured' }, { label: 'No asegurado', value: 'uninsured' }]} onChange={event => setFilters(current => ({ ...current, coverage: event.value }))} /></QuoteField><QuoteField label="Modalidad"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.mode} options={[{ label: 'Todas', value: '' }, { label: 'Manual', value: 'manual' }, { label: 'Automática', value: 'automatic' }]} onChange={event => setFilters(current => ({ ...current, mode: event.value }))} /></QuoteField><Button className="tw-h-9" label="Aplicar filtros" size="small" onClick={() => { setApplied({ ...filters }); }} /></div></Card>{historyLoading && <div role="status" className="tw-flex tw-items-center tw-gap-3 tw-p-3"><ProgressSpinner style={{width:28,height:28}} strokeWidth="5"/>Cargando historial…</div>}<Card className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-0' }, content: { className: 'tw-p-0' } }}><DataTable stripedRows value={historyLoading?[]:history} dataKey="id" size="small" scrollable emptyMessage="No hay cotizaciones para esos filtros"><Column header="Fecha" body={row => stamp(row.created_at)} /><Column header="Tarea" body={row => row.task_number || '—'} /><Column field="created_by" header="Usuario" /><Column header="Tipo" body={row => `${row.uninsured ? 'No asegurado' : 'Asegurado'}${row.gavilan ? ' · Gavilán' : row.special ? ' · Especial' : ''}`} /><Column header="Modalidad" body={row => row.origin_input === 'Cotización manual' ? 'Manual' : 'Automática'} /><Column header="Distancia" body={row => `${Number(row.total_km).toFixed(1)} km`} /><Column header="Peajes" body={row => `${row.toll_count || 0} · ${money(row.toll_price)}`} /><Column header="Total" body={row => money(row.total_price, { cents: true })} /><Column header="Acción" body={row => <Button className="tw-h-9" label="Recuperar" icon="pi pi-replay" text size="small" onClick={() => recover(row)} />} /></DataTable></Card></> : <><div className="draft-notice"><span>La carga se guarda automáticamente como borrador en este equipo.</span><Button className="tw-h-9" label="Descartar borrador" text size="small" onClick={() => { invalidate(); requestGuard.current.allowNew(); setForm(blank); try { localStorage.removeItem(model.draftKey); } catch { /* Sin almacenamiento local. */ } }} /></div><SelectButton value={mode} options={[{ label: 'Automática por ubicaciones', value: 'automatic' }, { label: 'Manual por kilómetros', value: 'manual' }]} optionLabel="label" optionValue="value" allowEmpty={false} onChange={event => event.value && switchMode(event.value)} /><div className="quote-prime-layout tw-grid tw-min-w-0 tw-gap-3 xl:tw-grid-cols-[minmax(0,44fr)_minmax(0,56fr)]"><form className="quote-form-panel tw-flex tw-min-w-0 tw-flex-col tw-gap-4" onSubmit={event => { event.preventDefault(); calculate(); }}><Card className="quote-step-card tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" title="1 · Identificación"><QuoteField label="Número de tarea (opcional)"><InputText className="tw-h-9" value={form.task_number} onChange={event => update('task_number', event.target.value)} placeholder="Ej.: 123456" maxLength={120} /></QuoteField></Card><Card className="quote-step-card tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" title="2 · Cobertura y vehículo"><div className="tw-grid tw-gap-3"><QuoteField label="Cobertura"><Dropdown appendTo={document.body} className="tw-h-9" value={form.coverage} options={[{ label: 'Asegurado', value: 'insured' }, { label: 'No asegurado', value: 'uninsured' }]} onChange={event => update('coverage', event.value)} /></QuoteField><label className="tw-flex tw-items-center tw-gap-2"><Checkbox checked={Boolean(form.special)} onChange={event => { invalidate(); setForm(current => ({ ...current, special: event.checked, gavilan: false })); }} />Especial</label><label className="tw-flex tw-items-center tw-gap-2"><Checkbox checked={Boolean(form.gavilan)} onChange={event => { invalidate(); setForm(current => ({ ...current, gavilan: event.checked, special: false })); }} />Gavilán</label></div></Card><Card className="quote-step-card tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" title="3 · Recorrido de la grúa"><TripFields mode={mode} form={form} update={update} selectPoint={selectPoint} changeLocationMode={changeLocationMode} /></Card>{mode === "manual" && <p className="tw-text-slate-600 dark:tw-text-slate-300">La tarifa manual vigente corresponde solo a recorridos dentro de Uruguay. Si el trayecto incluye otro país, requiere cálculo externo o una tarifa regional aprobada.</p>}<Button className="tw-h-9" type="submit" label={busy ? 'Calculando…' : mode === 'manual' ? 'Calcular cotización manual' : 'Trazar recorrido y calcular'} loading={busy} disabled={busy || !model.canCreate} />{requestGuard.current.submitted && <Button className="tw-h-9" type="button" label="Iniciar otra cotización con estos datos" text size="small" onClick={startNew} />}{confirmationUnknown && <Button className="tw-h-9" type="button" label="Revisar historial" outlined size="small" onClick={() => setTab("history")} />}</form><Result result={result} error={error} uncertain={confirmationUnknown} onManual={() => switchMode('manual')} onCopy={copy} onMarkerMove={markerMove} /></div></>}
  </div>;
}
