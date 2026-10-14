import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Calendar } from 'primereact/calendar';
import { Card } from 'primereact/card';
import { Column } from 'primereact/column';
import { DataTable } from './dense-table.jsx';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { ProgressSpinner } from 'primereact/progressspinner';
import { SelectButton } from 'primereact/selectbutton';
import { createScheduleResponseGate, indexSchedules, scheduleDay, schedulePeople, shiftScheduleDay } from './schedule-grid.js';

const dayISO = value => value instanceof Date ? iso(value) : /^\d{4}-\d{2}-\d{2}/.test(String(value || '')) ? String(value).slice(0, 10) : '';
const date = value => dayISO(value) ? new Date(`${dayISO(value)}T12:00:00`) : null;
const iso = value => value ? `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}` : '';
const shift = shiftScheduleDay;
const clock = value => value == null ? '' : `${String(Math.floor(Number(value) / 2) % 24).padStart(2, '0')}:${Number(value) % 2 ? '30' : '00'}${Number(value) >= 48 ? ' +1' : ''}`;
const summary = row => {
  if (row.draft_day) return <strong>Borrador sin publicar</strong>;
  if (row.published_day) return <strong>Libre publicado</strong>;
  const segments = Array.isArray(row.segments) ? row.segments : [];
  const hours = segments.length ? segments.map(item => `${clock(item.start)}–${clock(item.end)}`).join(' · ') : row.start_time ? `${String(row.start_time).slice(0, 5)}–${String(row.end_time || '').slice(0, 5)}` : row.shift_name || 'Sin horario';
  return <div className="tw-grid"><strong>{hours}</strong>{row.break_slot != null && <small>Descanso {clock(row.break_slot)}–{clock(Number(row.break_slot) + (row.break_duration || 1))}</small>}{row.notes && <small>{row.notes}</small>}{(row.exceptions || []).map((item, index) => <small key={index}>{item.type}: {clock(item.start)}–{clock(item.end)}</small>)}</div>;
};
const personalSummary = (row, continuation) => continuation
  ? <div className="tw-grid"><small>Continúa del día anterior</small><strong>Hasta {clock(row.end_slot)}</strong>{row.break_slot != null && Number(row.break_slot) + Number(row.break_duration || 1) > 48 && <small>Descanso {clock(Math.max(48, row.break_slot))}–{clock(Number(row.break_slot) + Number(row.break_duration || 1))}</small>}{(row.exceptions || []).filter(item => item.end > 48).map((item, index) => <small key={index}>{item.type}: {clock(Math.max(48, item.start))}–{clock(item.end)}</small>)}</div>
  : summary(row);
const operationalSlots = row => (row.segments || []).reduce((total, segment) => {
  for (let slot = segment.start; slot < segment.end; slot += 1) {
    const onBreak = row.break_slot != null && row.break_slot <= slot && slot < Number(row.break_slot) + Number(row.break_duration || 1);
    const excepted = (row.exceptions || []).some(item => item.start <= slot && slot < item.end);
    if (!onBreak && !excepted) total += 1;
  }
  return total;
}, 0);

export function SchedulesView({ model }) {
  const [filters, setFilters] = useState(model.filters);
  const [rows, setRows] = useState(model.rows);
  const [isLoading, setIsLoading] = useState(model.filters.view === 'week');
  const [requests, setRequests] = useState(model.requests || []);
  const [loadError, setLoadError] = useState('');
  const responseGate = useRef(null);
  const localRequestActive = useRef(false);
  const [requestOpen, setRequestOpen] = useState(false);
  const [requestForm, setRequestForm] = useState({ requested_date: '', request_type: 'AUSENCIA', reason: '', requested_start: null, requested_end: null });
  const [requestError, setRequestError] = useState('');
  const [requestBusy, setRequestBusy] = useState(false);
  const cancelRequest = async requestId => { if (!window.confirm('¿Cancelar esta solicitud pendiente?')) return; setRequestBusy(true); setRequestError(''); try { await model.request('/api/wfm/requests', { method: 'POST', body: JSON.stringify({ operation: 'cancel', request_id: requestId }) }); setRequests(await model.request('/api/wfm/requests?scope=mine')); } catch (error) { setRequestError(error.message); } finally { setRequestBusy(false); } };
  const set = (key, value) => setFilters(current => ({ ...current, [key]: value }));
  const paramsFor = values => { const params = new URLSearchParams(); if (values.view === 'week') params.set('week', values.week); else { if (values.from) params.set('date_from', values.from); if (values.to) params.set('date_to', values.to); } if (values.employee === 'mine') params.set('employee_id', model.userId); else if (values.employee !== 'team') params.set('employee_id', values.employee); if (values.role) params.set('role', values.role); if (values.search) params.set('q', values.search); return params; };
  if (!responseGate.current) responseGate.current = createScheduleResponseGate(paramsFor(model.filters).toString());
  const fetchRows = async values => {
    const ticket = responseGate.current.begin(paramsFor(values).toString());
    localRequestActive.current = true;
    setLoadError('');
    setIsLoading(true);
    setRows([]);
    try {
      const params = paramsFor(values);
      const previous = values.view === 'week' ? shift(values.week, -1) : null;
      const previousParams = previous ? new URLSearchParams(params) : null;
      if (previousParams) { previousParams.delete('week'); previousParams.set('date_from', previous); previousParams.set('date_to', previous); }
      if (previous && model.manager) params.set('include_free_days', '1');
      const start = previous || values.week;
      const end = shift(values.week, 6);
      const [response, earlier] = await Promise.all([
        !model.manager && previous
          ? model.request(`/api/wfm/mine?from=${start}&to=${end}`)
          : model.request(`/${previous && model.manager ? 'api/wfm/published' : 'api/schedules'}?${params}`),
        previousParams && model.manager ? model.request(`/api/schedules?${previousParams}`) : Promise.resolve([])
      ]);
      const normalized = !model.manager && previous
        ? response.map(row => ({ ...row, user_id: model.userId, display_name: model.currentUser,
            role_name: model.currentRole, schedule_date: row.date, start_slot: row.start,
            end_slot: row.end, break_slot: row.break }))
        : response;
      if (responseGate.current.accepts(ticket)) setRows([...normalized, ...earlier.filter(row => Number(row.end_slot) > 48)]);
    } catch (error) { if (responseGate.current.accepts(ticket)) setLoadError(error.message); }
    finally { if (responseGate.current.accepts(ticket)) { localRequestActive.current = false; setIsLoading(false); } }
  };
  useEffect(() => {
    if (localRequestActive.current || !responseGate.current.matches(paramsFor(model.filters).toString())) return;
    if (model.filters.view === 'week') fetchRows(model.filters);
    else { setRows(model.rows); setLoadError(''); }
  }, [model.rows, model.filters]);
  useEffect(() => () => { responseGate.current.invalidate(); }, []);
  const apply = values => { setFilters({ ...values }); model.onStateChange?.(values); fetchRows(values); };
  const navigate = daysOffset => apply({ ...filters, week: shift(filters.week, daysOffset), view: 'week' });
  const clear = () => apply({ view: 'history', week: model.currentWeek, from: '', to: '', employee: 'team', role: '', search: '' });
  const days = Array.from({ length: 7 }, (_, index) => shift(filters.week, index));
  const rangeRows = useMemo(() => filters.view === 'week' ? rows.filter(row => scheduleDay(row.schedule_date) >= days[0] && scheduleDay(row.schedule_date) <= days[6]) : rows, [rows, filters.view, filters.week]);
  const people = useMemo(() => schedulePeople(model.people, rows), [model.people, rows]);
  const scheduleIndex = useMemo(() => indexSchedules(rows), [rows]);
  const visiblePeople = people.filter(person => (filters.employee === 'team' || filters.employee === 'mine' && Number(person.id) === Number(model.userId) || Number(person.id) === Number(filters.employee)) && (!filters.role || person.role_name === filters.role) && (!filters.search || scheduleIndex.peopleWithRows.has(Number(person.id)) || person.display_name?.toLocaleLowerCase().includes(filters.search.toLocaleLowerCase())));
  const requestsByDay = useMemo(() => { const index = new Map(); for (const item of requests) { const day = dayISO(item.requested_date); if (!index.has(day)) index.set(day, []); index.get(day).push(item); } return index; }, [requests]);
  const personalDays = days.map(day => ({ day, entries: scheduleIndex.byDay.get(day) || [], requests: requestsByDay.get(day) || [] }));
  const plannedHours = rangeRows.reduce((total, row) => total + (row.segments || []).reduce((sum, segment) => sum + Number(segment.end - segment.start || 0), 0), 0) / 2;
  const overtimeHours = rangeRows.reduce((total, row) => total + Number(row.overtime_slots || 0), 0) / 2;
  const operativeHours = rangeRows.reduce((total, row) => total + operationalSlots(row), 0) / 2;
  const submitRequest = async event => { event.preventDefault(); setRequestBusy(true); setRequestError(''); try { await model.request('/api/wfm/requests', { method: 'POST', body: JSON.stringify(requestForm) }); setRequests(await model.request('/api/wfm/requests?scope=mine')); setRequestOpen(false); } catch (error) { setRequestError(error.message); } finally { setRequestBusy(false); } };
  return <div className="operational-view tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]">{loadError && <p role="alert">{loadError}</p>}<Card className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-3"><strong>{rangeRows.filter(row => !row.draft_day && !row.published_day).length} horarios publicados</strong>{model.canExport && <Button className="tw-h-9" label="Descargar reporte" icon="pi pi-download" outlined size="small" onClick={() => model.onExport(paramsFor(filters))} />}</div><div className="tw-mt-3 tw-grid tw-gap-3"><SelectButton value={filters.view} options={[{ label: 'Semana', value: 'week' }, { label: 'Historial', value: 'history' }]} onChange={event => event.value && apply({ ...filters, view: event.value })} />{filters.view === 'week' && <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-2"><Button className="tw-h-9" icon="pi pi-chevron-left" outlined size="small" aria-label="Semana anterior" onClick={() => navigate(-7)} /><strong>Semana del {filters.week}</strong><Button className="tw-h-9" icon="pi pi-chevron-right" outlined size="small" aria-label="Semana siguiente" onClick={() => navigate(7)} /><Button className="tw-h-9" label="Esta semana" text size="small" onClick={() => apply({ ...filters, week: model.currentWeek, view: 'week' })} /></div>}<div className="tw-flex tw-flex-wrap tw-items-end tw-gap-4"><label>Persona<Dropdown appendTo={document.body} className="tw-block tw-h-9" value={filters.employee} options={[{ label: 'Todo el equipo', value: 'team' }, { label: 'Mis horarios', value: 'mine' }, ...people.map(person => ({ label: person.display_name, value: String(person.id) }))]} onChange={event => set('employee', event.value)} filter /></label><label>Rol<Dropdown appendTo={document.body} className="tw-block tw-h-9" value={filters.role} options={[{ label: 'Todos los roles', value: '' }, ...[...new Set(people.map(person => person.role_name).filter(Boolean))].map(value => ({ label: value, value }))]} onChange={event => set('role', event.value)} /></label>{filters.view === 'history' && <><label>Desde<Calendar appendTo={document.body} className="tw-inline-flex tw-h-9 tw-w-full tw-min-w-0" inputClassName="tw-w-full tw-min-w-0 tw-flex-1" pt={{ dropdownButton: { className: 'tw-static tw-inline-flex tw-h-9 tw-w-9 tw-shrink-0 tw-items-center tw-justify-center tw-p-0' } }} value={date(filters.from)} onChange={event => set('from', iso(event.value))} dateFormat="dd/mm/yy" showIcon /></label><label>Hasta<Calendar appendTo={document.body} className="tw-inline-flex tw-h-9 tw-w-full tw-min-w-0" inputClassName="tw-w-full tw-min-w-0 tw-flex-1" pt={{ dropdownButton: { className: 'tw-static tw-inline-flex tw-h-9 tw-w-9 tw-shrink-0 tw-items-center tw-justify-center tw-p-0' } }} value={date(filters.to)} onChange={event => set('to', iso(event.value))} dateFormat="dd/mm/yy" showIcon /></label></>}<label>Buscar<InputText className="tw-block tw-h-9" value={filters.search} onChange={event => set('search', event.target.value)} onKeyDown={event => event.key === 'Enter' && apply(filters)} placeholder="Turno, nota o persona" /></label><Button className="tw-h-9" label="Aplicar filtros" size="small" onClick={() => apply(filters)} /><Button className="tw-h-9" label="Limpiar" text size="small" onClick={clear} /></div></div></Card>
{!isLoading && !loadError && !model.manager && filters.view === 'week' && <><Card className="tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><div className="tw-flex tw-flex-wrap tw-gap-3"><strong>{plannedHours} h planificadas</strong><span>{operativeHours} h operativas</span><span>{overtimeHours} h extra</span></div></Card><div className="tw-grid tw-gap-3 sm:tw-grid-cols-2 xl:tw-grid-cols-4">{personalDays.map(({ day, entries, requests: dayRequests }, index) => <Card key={day} title={['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][index] + ' ' + day.slice(8) + '/' + day.slice(5, 7)} className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm">{dayRequests.map(item => <p key={item.request_id}>Solicitud {item.request_type} · {item.status}</p>)}{entries.length ? entries.map(({ row, continuation }) => <div key={`${row.id}:${continuation}`} className="tw-mb-2 tw-rounded-md tw-border tw-p-2">{personalSummary(row, continuation)}</div>) : <p>Sin publicación para este día</p>}</Card>)}</div></>}
    {!isLoading && !loadError && (model.manager || filters.view !== 'week') && <Card className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-0' }, content: { className: 'tw-p-0' } }}><DataTable stripedRows value={filters.view === 'week' ? visiblePeople : rangeRows} dataKey="id" paginator rows={50} size="small" emptyMessage="No hay horarios para los filtros seleccionados" className="schedule-react-table"><Column header="Persona" body={row => row.display_name || 'Usuario inactivo'} />{filters.view === 'week' ? days.map((day, index) => <Column key={day} header={`${['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'][index]} ${day.slice(8)}/${day.slice(5, 7)}`} body={person => { const entries = scheduleIndex.byPersonDay.get(`${person.id}:${day}`) || []; return entries.length ? entries.map(({ row, continuation }) => <div key={`${row.id}:${continuation}`}>{continuation ? personalSummary(row, true) : summary(row)}</div>) : 'Sin publicación'; }} />) : <><Column header="Fecha" body={row => String(row.schedule_date).slice(0, 10)} /><Column field="role_name" header="Rol" /><Column header="Horario publicado" body={summary} /><Column header="Origen" body={row => row.source === 'legacy' ? 'Histórico' : `WFM #${row.revision}`} /></>}</DataTable></Card>}
    {isLoading && <div role="status" className="tw-flex tw-items-center tw-gap-3 tw-p-4"><ProgressSpinner style={{width:28,height:28}} strokeWidth="5"/>Cargando horarios…</div>}
    {model.canRequest && <Card title="Mis solicitudes" className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><Button className="tw-h-9" label="Nueva solicitud" icon="pi pi-plus" size="small" onClick={() => setRequestOpen(true)} /><DataTable stripedRows value={requests} dataKey="request_id" paginator rows={50} size="small" scrollable emptyMessage="No hay solicitudes"><Column field="requested_date" header="Fecha" className="tw-whitespace-nowrap" /><Column field="request_type" header="Tipo" /><Column field="reason" header="Motivo" className="operational-long-text" style={{ minWidth: '250px', whiteSpace: 'normal', wordWrap: 'break-word' }} /><Column field="status" header="Estado" /><Column header="Resolución" body={row => <span>{row.resolution_note || '—'}{row.resolved_by ? ' · ' + row.resolved_by : ''}</span>} /><Column header="Acción" body={row => row.status === 'PENDIENTE' && <Button className="tw-h-9" label="Cancelar" text severity="danger" size="small" disabled={requestBusy} onClick={() => cancelRequest(row.request_id)} />} /></DataTable>{requestError && <p role="alert">{requestError}</p>}</Card>}
    <Dialog header="Nueva solicitud de horario" visible={requestOpen} onHide={() => setRequestOpen(false)} modal appendTo={document.body} style={{ width: 'min(560px, 95vw)' }}><form onSubmit={submitRequest} className="tw-flex tw-flex-col tw-gap-4"><label>Fecha<Calendar appendTo={document.body} className="tw-inline-flex tw-h-9 tw-w-full tw-min-w-0" inputClassName="tw-w-full tw-min-w-0 tw-flex-1" pt={{ dropdownButton: { className: 'tw-static tw-inline-flex tw-h-9 tw-w-9 tw-shrink-0 tw-items-center tw-justify-center tw-p-0' } }} value={date(requestForm.requested_date)} onChange={event => setRequestForm(current => ({ ...current, requested_date: iso(event.value) }))} dateFormat="dd/mm/yy" showIcon /></label><label>Tipo<Dropdown appendTo={document.body} className="tw-block tw-h-9" value={requestForm.request_type} options={[{ label: 'Ausencia', value: 'AUSENCIA' }, { label: 'Cambio de turno', value: 'CAMBIO_TURNO' }]} onChange={event => setRequestForm(current => ({ ...current, request_type: event.value }))} /></label>{requestForm.request_type === 'CAMBIO_TURNO' && <><label>Inicio solicitado (franja de 30 min)<InputText className="tw-h-9" type="number" min="0" max="47" value={requestForm.requested_start ?? ''} onChange={event => setRequestForm(current => ({ ...current, requested_start: Number(event.target.value) }))} required /></label><label>Fin solicitado (franja de 30 min)<InputText className="tw-h-9" type="number" min="1" max="72" value={requestForm.requested_end ?? ''} onChange={event => setRequestForm(current => ({ ...current, requested_end: Number(event.target.value) }))} required /></label></>}<label>Motivo<InputTextarea value={requestForm.reason} onChange={event => setRequestForm(current => ({ ...current, reason: event.target.value }))} required minLength={3} maxLength={500} /></label>{requestError && <p role="alert">{requestError}</p>}<div className="tw-flex tw-justify-end tw-gap-2"><Button className="tw-h-9" type="button" label="Cancelar" text onClick={() => setRequestOpen(false)} /><Button className="tw-h-9" type="submit" label="Enviar solicitud" loading={requestBusy} /></div></form></Dialog>
  </div>;
}
