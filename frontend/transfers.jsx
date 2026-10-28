import React, { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Calendar } from 'primereact/calendar';
import { Card } from 'primereact/card';
import { Column } from 'primereact/column';
import { DataTable } from './dense-table.jsx';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Menu } from 'primereact/menu';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { formatDateTime } from './date-format.js';

const types = ['Traslado Largo', 'Traslado Depósito', 'Traslado Directo', 'Mercosur'];
const statusNames = { SIN_ASIGNAR: 'Sin asignar', ASIGNADO: 'Asignado', EN_CURSO: 'En curso', FINALIZADO: 'Finalizado', CANCELADO: 'Cancelado' };
const transitions = { SIN_ASIGNAR: ['ASIGNADO', 'CANCELADO'], ASIGNADO: ['SIN_ASIGNAR', 'EN_CURSO', 'CANCELADO'], EN_CURSO: ['ASIGNADO', 'FINALIZADO', 'CANCELADO'], FINALIZADO: [], CANCELADO: [] };
const blank = { task_number: '', transfer_type: types[0], scheduled_date: '', scheduled_time: '', origin: '', destination: '', provider: '', responsible: '', comments: '' };
const dateOf = value => value ? new Date(`${value}T12:00:00`) : null;
const dateText = value => value ? `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}` : '';
const stamp = formatDateTime;
const options = values => values.map(value => ({ label: value, value }));
const normalized = value => ({ PENDIENTE: 'SIN_ASIGNAR', CONFIRMADO: 'ASIGNADO', COMPLETADO: 'FINALIZADO' }[value] || value || 'SIN_ASIGNAR');

function Field({ label, children, wide = false }) { return <label className={`tw-flex tw-min-w-0 tw-flex-col tw-gap-1 tw-text-xs ${wide ? 'md:tw-col-span-2' : ''}`}><span>{label}</span>{children}</label>; }
function RowMenu({ id, label, items, text }) { const menu = useRef(null); return <><Menu ref={menu} id={`transfer-menu-${id}`} model={items} popup appendTo={document.body} /><Button className="tw-h-9" type="button" label={text} icon="pi pi-ellipsis-v" text rounded={!text} size="small" aria-label={label} aria-haspopup="menu" aria-controls={`transfer-menu-${id}`} onClick={event => menu.current?.toggle(event)} /></>; }

export function TransfersView({ model }) {
  const [filters, setFilters] = useState(model.filters);
  const [rows, setRows] = useState(model.rows);
  useEffect(() => setFilters(model.filters), [model.filters]);
  useEffect(() => setRows(model.rows), [model.rows]);
  const [dialog, setDialog] = useState(null);
  const [form, setForm] = useState(blank);
  const [events, setEvents] = useState([]);
  const [responsibles, setResponsibles] = useState([]);
  const [duplicate, setDuplicate] = useState(null);
  const [conflictCurrent, setConflictCurrent] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useRef(null);
  const notify = (severity, summary, detail) => toast.current?.show({ severity, summary, detail, life: severity === 'error' ? 5500 : 3200 });
  const change = (name, value) => { setForm(current => ({ ...current, [name]: value })); setDuplicate(null); };
  const changeFilter = (name, value) => setFilters(current => ({ ...current, [name]: value }));
  const close = () => { setDialog(null); setForm(blank); setEvents([]); setDuplicate(null); setConflictCurrent(null); };
  const open = (kind, row = null, status = '') => { setDuplicate(null);setConflictCurrent(null);setForm({ ...blank, ...row, scheduled_date: row?.scheduled_date || dateText(new Date()), scheduled_time: row?.scheduled_time?.slice(0, 5) || '', status, note: '' }); setDialog({ kind, row, status }); };
  const openTransition = async (row, status) => {
    try { if (status === 'ASIGNADO') setResponsibles(await model.request('/api/transfers/responsibles')); open('status', row, status); }
    catch (error) { notify('error', 'No se pudieron cargar responsables', error.message); }
  };
  const openHistory = async row => {
    try { setEvents(await model.request(`/api/transfers/${row.id}/events`)); open('history', row); }
    catch (error) { notify('error', 'No se pudo cargar el historial', error.message); }
  };
  const request = async (url, method, body, success) => {
    if (busy) return;
    setBusy(true);
    try {
      await model.request(url, { method, body: JSON.stringify(body) });
      notify('success', success);
      window.toast?.(success);
      close();
      await model.refresh();
    } catch (error) {
      if (error.status === 409 && error.payload?.detail?.duplicate) setDuplicate(error.payload.detail.duplicate);
      else if(!error.stale){notify('error', error.status===409?'Conflicto de edición':'No se pudo guardar', error.message || 'Revisá los datos e intentá de nuevo');if(error.status===409){await model.refresh().catch(()=>{});if(dialog?.row?.id)await model.request(`/api/transfers/${dialog.row.id}`).then(setConflictCurrent).catch(()=>{});}}
    } finally { setBusy(false); }
  };
  const save = event => {
    event.preventDefault();
    if (!dialog) return;
    const { kind, row, status } = dialog;
    if (kind === 'create' || kind === 'edit') {
      if (!form.task_number.trim() || !form.origin.trim() || !form.destination.trim() || !form.scheduled_date) { notify('error', 'Faltan datos', 'Completá tarea, fecha, origen y destino.'); return; }
      const body = { task_number: form.task_number.trim(), transfer_type: form.transfer_type, scheduled_date: form.scheduled_date, scheduled_time: form.scheduled_time || null, origin: form.origin.trim(), destination: form.destination.trim(), provider: form.provider || null, comments: form.comments || null, allow_duplicate: Boolean(duplicate) };
      if (kind === 'create') request('/api/transfers', 'POST', { ...body, planner: model.currentUser, status: 'SIN_ASIGNAR' }, 'Programado creado');
      else request(`/api/transfers/${row.id}`, 'PATCH', { ...body, responsible: form.responsible || null, expected_revision: row.revision }, 'Programado actualizado');
    } else if (kind === 'status') {
      if (status === 'ASIGNADO' && (!form.provider?.trim() || !form.responsible)) { notify('error', 'Faltan datos', 'Seleccioná prestador y responsable.'); return; }
      if (['FINALIZADO', 'CANCELADO'].includes(status) && (form.note || '').trim().length < 2) { notify('error', 'Faltan datos', 'Indicá el resultado o motivo.'); return; }
      request(`/api/transfers/${row.id}/status`, 'PATCH', { status, provider: form.provider || null, responsible: form.responsible || null, note: form.note || null, expected_revision: row.revision }, `Estado: ${statusNames[status]}`);
    } else if (kind === 'duplicate') request('/api/transfers', 'POST', { task_number: form.task_number.trim(), transfer_type: row.transfer_type, scheduled_date: row.scheduled_date, scheduled_time: row.scheduled_time, origin: row.origin, destination: row.destination, provider: null, responsible: null, planner: model.currentUser, status: 'SIN_ASIGNAR', comments: row.comments, allow_duplicate: Boolean(duplicate) }, 'Programado duplicado como Sin asignar');
  };
  const groups = [['long', 'Traslados largos', row => !/(depósito|deposito|directo|mercosur)/i.test(row.transfer_type || '')], ['deposit', 'Traslados a depósito', row => /(depósito|deposito)/i.test(row.transfer_type || '')], ['direct', 'Traslados directos', row => /directo/i.test(row.transfer_type || '')], ['mercosur', 'Mercosur', row => /mercosur/i.test(row.transfer_type || '')]].map(([key, label, test]) => ({ key, label, rows: rows.filter(test) })).filter(group => group.rows.length);
  const pending = rows.filter(row => !['FINALIZADO','CANCELADO'].includes(normalized(row.status))).length;
  const counts = { SIN_ASIGNAR: rows.filter(row => normalized(row.status)==='SIN_ASIGNAR').length, EN_CURSO: rows.filter(row => normalized(row.status)==='EN_CURSO').length, closed: rows.length-pending };
  const actionItems = row => {
    const terminal = ['FINALIZADO', 'CANCELADO'].includes(normalized(row.status));
    return [...(model.canManage && !terminal ? [{ label: 'Editar', icon: 'pi pi-pencil', command: () => open('edit', row) }] : []), { label: 'Historial', icon: 'pi pi-history', command: () => openHistory(row) }, ...(model.canManage ? [{ label: 'Duplicar como nuevo', icon: 'pi pi-copy', command: () => open('duplicate', row) }] : []), ...(model.canManage && !terminal ? [{ label: 'Cancelar programado', icon: 'pi pi-times', command: () => openTransition(row, 'CANCELADO') }] : [])];
  };
  const table = group => <Card key={group.key} className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-0' }, content: { className: 'tw-p-0' } }}><div className="tw-p-3"><strong>{group.label}</strong><span className="tw-ml-2">{group.rows.length} programados</span></div><DataTable stripedRows value={group.rows} dataKey="id" size="small" className="phase-two-table transfer-prime-table" tableClassName="transfer-data-table" scrollable emptyMessage={`No hay ${group.label.toLowerCase()}`} aria-label={group.label}><Column field="scheduled_date" header="Fecha" className="tw-whitespace-nowrap" /><Column header="Hora" className="tw-whitespace-nowrap" body={row => row.scheduled_time?.slice(0, 5) || '—'} /><Column header="Tarea" body={row => <a href={`https://aps.portoservicios.uy/3/tareas/${encodeURIComponent(row.task_number)}`} target="_blank" rel="noopener noreferrer">{row.task_number}</a>} /><Column field="origin" header="Desde" /><Column field="destination" header="Hacia" /><Column header="Prestador" body={row => row.provider || 'Sin asignar'} /><Column header="Responsable" body={row => row.responsible || 'Sin asignar'} /><Column field="planner" header="Planifica" /><Column header="Estado" body={row => model.canManage && transitions[normalized(row.status)]?.length ? <RowMenu id={`status-${row.id}`} label={`Cambiar estado de ${row.task_number}`} text={statusNames[normalized(row.status)]} items={transitions[normalized(row.status)].map(status => ({ label: statusNames[status], command: () => openTransition(row, status) }))} /> : <Tag value={statusNames[normalized(row.status)]} severity={normalized(row.status) === 'SIN_ASIGNAR' ? 'danger' : normalized(row.status) === 'FINALIZADO' ? 'success' : 'info'} />} /><Column header="Opciones" body={row => <RowMenu id={`actions-${row.id}`} label={`Opciones de ${row.task_number}`} items={actionItems(row)} />} frozen alignFrozen="right" /></DataTable></Card>;
  return <div className="operational-view transfer-prime-view tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]"><Toast ref={toast} /><section className="tw-grid tw-grid-cols-1 tw-gap-3 sm:tw-grid-cols-2 xl:tw-grid-cols-4" aria-label="Indicadores de programados">{[['Pendientes', pending], ['Sin asignar', counts.SIN_ASIGNAR], ['En curso', counts.EN_CURSO], ['Cerrados', counts.closed]].map(([label, count]) => <Card key={label} className="tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-3' } }}><span>{label}</span><strong className="tw-block tw-text-2xl">{count}</strong></Card>)}</section>
    <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-2"><strong>{rows.length} programados</strong><div className="tw-flex tw-gap-2">{model.canExport && <Button className="tw-h-9" label="Descargar reporte" icon="pi pi-download" size="small" outlined onClick={model.onExport} />}{model.canCreate && <Button className="tw-h-9" label="Nuevo programado" icon="pi pi-plus" size="small" onClick={() => open('create')} />}</div></div>
    <Card className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-3' } }}><div className="tw-flex tw-flex-wrap tw-items-end tw-gap-4"><Field label="Vista"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.view} options={model.viewOptions} onChange={event => changeFilter('view', event.value)} /></Field><Field label="Desde"><Calendar appendTo={document.body} className="tw-h-9" value={dateOf(filters.from)} onChange={event => changeFilter('from', dateText(event.value))} dateFormat="dd/mm/yy" showIcon /></Field><Field label="Hasta"><Calendar appendTo={document.body} className="tw-h-9" value={dateOf(filters.to)} onChange={event => changeFilter('to', dateText(event.value))} dateFormat="dd/mm/yy" showIcon /></Field><Field label="Estado"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.status} options={model.statusOptions} onChange={event => changeFilter('status', event.value)} /></Field><Field label="Tipo"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.type} options={[{ label: 'Todos los tipos', value: '' }, ...options(types)]} onChange={event => changeFilter('type', event.value)} /></Field>{[['task', 'Tarea'], ['provider', 'Prestador'], ['responsible', 'Responsable'], ['search', 'Origen, destino o comentario']].map(([key, label]) => <Field key={key} label={label}><InputText className="tw-h-9" value={filters[key]} onChange={event => changeFilter(key, event.target.value)} onKeyDown={event => event.key === 'Enter' && model.onApply(filters)} /></Field>)}<Button className="tw-h-9" label="Aplicar filtros" size="small" outlined onClick={() => model.onApply(filters)} /><Button className="tw-h-9" label="Limpiar" size="small" text onClick={model.onClear} /></div></Card>
    {groups.length ? groups.map(table) : <Card className="tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><div className="tw-p-3 tw-text-center">No hay programados para los filtros seleccionados.</div></Card>}
    <Dialog header={dialog?.kind === 'create' ? 'Nuevo programado' : dialog?.kind === 'edit' ? 'Editar programado' : dialog?.kind === 'status' ? `${statusNames[dialog.status]} · tarea ${dialog.row.task_number}` : dialog?.kind === 'duplicate' ? 'Duplicar programado' : 'Historial del programado'} visible={Boolean(dialog)} onHide={close} modal appendTo={document.body} style={{ width: 'min(720px, 95vw)' }}><form onSubmit={save} className="tw-flex tw-flex-col tw-gap-4">
      {conflictCurrent&&<div role="alert" className="tw-rounded-md tw-border tw-border-amber-400 tw-bg-amber-50 tw-p-3 tw-text-[13px]"><strong>El programado cambió mientras lo editabas.</strong><p>Tu borrador sigue en el formulario. Versión actual: {statusNames[normalized(conflictCurrent.status)]} · Responsable: {conflictCurrent.responsible||'Sin asignar'}.</p><p>{conflictCurrent.origin} → {conflictCurrent.destination}</p><Button type="button" text size="small" label="Actualizar datos para comparar" onClick={()=>model.request(`/api/transfers/${dialog.row.id}`).then(setConflictCurrent).catch(error=>notify('error','No se pudo consultar',error.message))}/></div>}
      {['create', 'edit'].includes(dialog?.kind) && <div className="tw-grid tw-grid-cols-1 tw-gap-3 md:tw-grid-cols-2"><Field label="Tarea"><InputText className="tw-h-9" value={form.task_number} onChange={event => change('task_number', event.target.value)} maxLength={120} required /></Field><Field label="Tipo de traslado"><Dropdown appendTo={document.body} className="tw-h-9" value={form.transfer_type} options={options(types)} onChange={event => change('transfer_type', event.value)} /></Field><Field label="Fecha"><Calendar appendTo={document.body} className="tw-h-9" value={dateOf(form.scheduled_date)} onChange={event => change('scheduled_date', dateText(event.value))} dateFormat="dd/mm/yy" showIcon /></Field><Field label="Hora"><InputText className="tw-h-9" type="time" value={form.scheduled_time} onChange={event => change('scheduled_time', event.target.value)} /></Field><Field label="Origen"><InputText className="tw-h-9" value={form.origin} onChange={event => change('origin', event.target.value)} maxLength={500} required /></Field><Field label="Destino"><InputText className="tw-h-9" value={form.destination} onChange={event => change('destination', event.target.value)} maxLength={500} required /></Field><Field label="Prestador"><InputText className="tw-h-9" value={form.provider} onChange={event => change('provider', event.target.value)} maxLength={200} /></Field>{dialog.kind === 'edit' && <Field label="Responsable"><InputText className="tw-h-9" value={form.responsible || ''} onChange={event => change('responsible', event.target.value)} maxLength={120} /></Field>}<Field label="Comentarios" wide><InputTextarea value={form.comments || ''} onChange={event => change('comments', event.target.value)} rows={3} maxLength={4000} /></Field></div>}
      {dialog?.kind === 'status' && <><p>{dialog.row.origin} → {dialog.row.destination}</p>{dialog.status === 'ASIGNADO' && <><Field label="Prestador / Auxiliador"><InputText className="tw-h-9" value={form.provider || ''} onChange={event => change('provider', event.target.value)} required /></Field><Field label="Responsable interno"><Dropdown appendTo={document.body} className="tw-h-9" value={form.responsible || ''} options={[{ label: 'Seleccionar', value: '' }, ...responsibles.map(person => ({ label: `${person.display_name} · ${person.role_name}`, value: person.display_name }))]} onChange={event => change('responsible', event.value)} filter /></Field></>}{['FINALIZADO', 'CANCELADO'].includes(dialog.status) && <Field label={dialog.status === 'FINALIZADO' ? 'Resultado del traslado' : 'Motivo de cancelación'}><InputTextarea value={form.note || ''} onChange={event => change('note', event.target.value)} rows={5} required /></Field>}</>}
      {dialog?.kind === 'duplicate' && <><Field label="Número de tarea para la copia"><InputText className="tw-h-9" value={form.task_number} onChange={event => change('task_number', event.target.value)} required /></Field><p>{dialog.row.transfer_type} · {dialog.row.scheduled_date} · {dialog.row.origin} → {dialog.row.destination}</p></>}
      {dialog?.kind === 'history' && <div className="notice-timeline">{events.length ? events.map((entry, index) => <article key={entry.id || index}><strong>{entry.event_type}</strong><time>{stamp(entry.created_at)}</time><span>{entry.actor}</span>{entry.note && <p>{entry.note}</p>}</article>) : <p>No hay movimientos registrados.</p>}</div>}
      {duplicate && <div className="tw-rounded-md tw-border tw-border-amber-300 tw-bg-amber-50 tw-p-3"><strong>Posible programado duplicado</strong><p>Tarea {duplicate.task_number}. Si es un caso independiente, presioná Guardar nuevamente.</p></div>}
      <div className="tw-flex tw-justify-end tw-gap-2"><Button className="tw-h-9" type="button" label={dialog?.kind === 'history' ? 'Cerrar' : 'Cancelar'} text onClick={close} disabled={busy} />{dialog?.kind !== 'history' && <Button className="tw-h-9" type="submit" label={busy ? 'Guardando…' : 'Guardar'} loading={busy} disabled={busy} />}</div>
    </form></Dialog>
  </div>;
}
