import React, { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Calendar } from 'primereact/calendar';
import { Card } from 'primereact/card';
import { Column } from 'primereact/column';
import { DataTable } from './dense-table.jsx';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Menu } from 'primereact/menu';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';

const statusNames = { PENDIENTE: 'Pendiente', EN_GESTION: 'En gestión', ESPERANDO_RESPUESTA: 'Esperando respuesta', RESUELTO: 'Resuelto', CANCELADO: 'Cancelado', NORMALIZADO: 'Normalizado' };
const noticeTypes = ['Volverán a llamar', 'Reclama no cumplimiento', 'Se envió HSM', 'Solicita coordinación', 'Solicita información', 'Reclamo por demora', 'Otro motivo'];
const delayServices = ['TODAS', 'GRÚA', 'ML', 'SINIESTROS'];
const delayMessages = ['No confirmar tiempos', 'Margen de', 'A confirmar'];
const reviewOptions = [60, 120, 240, 480, 1440].map(value => ({ value, label: value < 60 ? `${value} min` : `${value / 60} h` }));
const delayBlank = { service: 'TODAS', department: 'MONTEVIDEO', zone: '', message: 'No confirmar tiempos', minutes: null, review_minutes: 120 };
const noticeBlank = { task_number: '', phone: '', notice_type: '', audience: 'TODOS', detail: '', managed_by: false };
const options = values => values.map(value => ({ label: value, value }));
const asDate = value => value ? new Date(`${value}T12:00:00`) : null;
const dateString = value => value ? `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}` : '';
const formatDate = value => value ? new Date(value).toLocaleString('es-UY', { dateStyle: 'short', timeStyle: 'short' }) : '—';
const formatNoticeTime = value => value ? new Date(value).toLocaleString('es-UY', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—';
const noticeIsClosed = row => ['RESUELTO', 'CANCELADO'].includes(row.status);
const noticeStatusDisplay = {
  PENDIENTE: { label: 'Pendiente', severity: 'danger' },
  EN_GESTION: { label: 'En gestión', severity: 'info' },
  ESPERANDO_RESPUESTA: { label: 'Esperando respuesta', severity: 'warning' },
  RESUELTO: { label: 'Resuelto', severity: 'success' },
  CANCELADO: { label: 'Cancelado', severity: 'secondary' }
};
const noticeState = row => {
  if (!row.managed_by && !noticeIsClosed(row)) return { label: 'Sin responsable', severity: 'danger' };
  return noticeStatusDisplay[row.status] || { label: statusNames[row.status] || row.status, severity: 'secondary' };
};
const errorText = error => error?.message || 'No se pudo completar la operación';

function Field({ label, children, wide = false }) {
  return <label className={`tw-flex tw-min-w-0 tw-flex-col tw-gap-1 tw-text-xs tw-font-medium ${wide ? 'md:tw-col-span-2' : ''}`}><span>{label}</span>{children}</label>;
}

let activeRowMenu = null;

function RowMenu({ id, items, label, text }) {
  const menu = useRef(null);
  useEffect(() => () => { if (activeRowMenu?.id === id) { menu.current?.hide(); activeRowMenu = null; } }, [id]);
  const toggle = event => {
    event.stopPropagation();
    if (activeRowMenu?.id === id) { menu.current?.hide(); activeRowMenu = null; return; }
    activeRowMenu?.menu?.current?.hide();
    menu.current?.show(event);
    activeRowMenu = { id, menu };
  };
  return <><Menu ref={menu} id={`row-menu-${id}`} model={items} popup={true} appendTo={document.body} onHide={() => { if (activeRowMenu?.id === id) activeRowMenu = null; }} /><Button className="tw-h-9" type="button" icon="pi pi-ellipsis-v" label={text} text rounded={!text} size="small" aria-label={label} aria-haspopup="menu" aria-controls={`row-menu-${id}`} onClick={toggle} /></>;
}

function useOperation(model) {
  const toast = useRef(null);
  const [busy, setBusy] = useState(false);
  const notify = (severity, summary, detail) => toast.current?.show({ severity, summary, detail, life: severity === 'error' ? 5500 : 3200 });
  const run = async (task, success, after) => {
    if (busy) return false;
    setBusy(true);
    try {
      await task();
      notify('success', success);
      window.toast?.(success);
      after?.();
    } catch (error) {
      notify('error', 'No se pudo guardar', errorText(error));
      setBusy(false);
      return false;
    }
    try {
      await model.refresh();
      return true;
    } catch (error) {
      notify('error', 'No se pudo actualizar la tabla', errorText(error));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { toast, busy, run, notify };
}

export function DelaysView({ model }) {
  const [filters, setFilters] = useState(model.filters);
  const [page, setPage] = useState(model.page);
  useEffect(() => setFilters(model.filters), [model.filters]);
  useEffect(() => setPage(model.page), [model.page]);
  const [dialog, setDialog] = useState(null);
  const [form, setForm] = useState(delayBlank);
  const [events, setEvents] = useState([]);
  const { toast, busy, run, notify } = useOperation(model);
  const update = (key, value) => setForm(current => ({ ...current, [key]: value }));
  const close = () => { setDialog(null); setForm(delayBlank); setEvents([]); };
  const open = (kind, row = null) => { setForm({ ...delayBlank, verification_note: '', resolution_note: '' }); setDialog({ kind, row }); };
  const history = async row => {
    try { setEvents(await model.request(`/api/delays/${row.id}/events`)); setDialog({ kind: 'history', row }); }
    catch (error) { notify('error', 'No se pudo cargar el historial', errorText(error)); }
  };
  const save = event => {
    event.preventDefault();
    const { kind, row } = dialog;
    if (kind === 'create') {
      if (!form.zone.trim() || (form.message === 'Margen de' && !form.minutes)) { notify('error', 'Faltan datos', 'Completá la zona y el margen cuando corresponda.'); return; }
      run(() => model.request('/api/delays', { method: 'POST', body: JSON.stringify({ ...form, zone: form.zone.trim(), minutes: form.message === 'Margen de' ? form.minutes : null, agent: model.currentUser, status: 'VIGENTE' }) }), 'Demora vigente registrada', close);
    } else if (kind === 'verify') {
      if ((form.verification_note || '').trim().length < 2) { notify('error', 'Faltan datos', 'Indicá cómo se verificó la demora.'); return; }
      run(() => model.request(`/api/delays/${row.id}/verify`, { method: 'PATCH', body: JSON.stringify({ verification_note: form.verification_note.trim(), review_minutes: form.review_minutes }) }), 'Vigencia renovada y registrada', close);
    } else if (kind === 'normalize') {
      if ((form.resolution_note || '').trim().length < 2) { notify('error', 'Faltan datos', 'Indicá la evidencia de cierre.'); return; }
      run(() => model.request(`/api/delays/${row.id}/normalize`, { method: 'PATCH', body: JSON.stringify({ status: 'NORMALIZADO', resolution_note: form.resolution_note.trim() }) }), 'Demora normalizada con evidencia de cierre', close);
    }
  };
  const changeFilter = (key, value) => setFilters(current => ({ ...current, [key]: value }));
  const turnPage = async (offset, limit) => { try { setPage(await model.onPage(offset, limit)); } catch (error) { notify('error', 'No se pudo cambiar de página', errorText(error)); } };
  const actionItems = row => [
    ...(row.status === 'VIGENTE' && model.canNormalize ? [
      { label: row.needs_review ? 'Confirmar vigencia' : 'Renovar control', icon: 'pi pi-check', command: () => open('verify', row) },
      { label: 'Normalizar', icon: 'pi pi-flag', command: () => open('normalize', row) }
    ] : []),
    { label: 'Historial', icon: 'pi pi-history', command: () => history(row) }
  ];
  const title = { create: 'Registrar demora vigente', verify: 'Renovar control de vigencia', normalize: 'Confirmar normalización', history: 'Historial de la demora' }[dialog?.kind];
  return <div className="operational-view delay-prime-view tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]">
    <Toast ref={toast} />
    <Card className="tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-3' } }}><div className="delay-prime-toolbar tw-flex tw-flex-wrap tw-items-end tw-gap-4">
      <Field label="Desde"><Calendar appendTo={document.body} className="tw-h-9" value={asDate(filters.from)} onChange={event => changeFilter('from', dateString(event.value))} dateFormat="dd/mm/yy" showIcon /></Field>
      <Field label="Hasta"><Calendar appendTo={document.body} className="tw-h-9" value={asDate(filters.to)} onChange={event => changeFilter('to', dateString(event.value))} dateFormat="dd/mm/yy" showIcon /></Field>
      <Field label="Vigencia"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.view} options={model.viewOptions} onChange={event => changeFilter('view', event.value)} /></Field>
      <Field label="Departamento"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.department} options={model.departmentOptions} onChange={event => changeFilter('department', event.value)} filter /></Field>
      <Field label="Prestación"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.service} options={model.serviceOptions} onChange={event => changeFilter('service', event.value)} /></Field>
      <Field label="Búsqueda"><InputText className="tw-h-9" value={filters.search} onChange={event => changeFilter('search', event.target.value)} onKeyDown={event => event.key === 'Enter' && model.onApply(filters)} placeholder="Texto, zona, agente o fecha" /></Field>
      <Button className="tw-h-9" label="Aplicar filtros" size="small" outlined onClick={() => model.onApply(filters)} /><Button className="tw-h-9" label="Limpiar" size="small" text onClick={model.onClear} />
    </div></Card>
    <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-2"><strong>{page.total} zonas</strong><div className="tw-flex tw-flex-wrap tw-gap-2">{model.canExport && <Button className="tw-h-9" label="Descargar reporte" icon="pi pi-download" size="small" outlined onClick={model.onExport} />}{model.canCreate && <Button className="tw-h-9" label="Registrar demora" icon="pi pi-plus" size="small" onClick={() => open('create')} />}</div></div>
    <Card className="tw-min-w-0 tw-max-w-full tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-0' }, content: { className: 'tw-p-0' } }}><DataTable stripedRows value={page.items} dataKey="id" size="small" className="phase-two-table delay-prime-table" tableClassName="delay-data-table" rowClassName={row => row.needs_review ? 'delay-review-row' : row.is_current ? 'active-delay' : ''} emptyMessage="No hay demoras para los filtros seleccionados" aria-label="Zonas con demora" scrollable lazy paginator rows={page.limit || 50} first={page.offset} totalRecords={page.total} onPage={event => turnPage(event.rows === page.limit ? event.first : 0, event.rows)}>
      <Column header="Registrada" body={row => formatDate(row.created_at)} /><Column header="Vigencia" body={row => row.status === 'NORMALIZADO' ? <Tag value="Normalizada" severity="secondary" /> : row.needs_review ? <Tag value="Requiere revisión" severity="warning" /> : <><Tag value="Verificada" severity="success" /><small className="delay-close-meta">hasta {formatDate(row.review_due_at)}</small></>} />
      <Column field="service" header="Prestación" /><Column field="department" header="Departamento" /><Column field="zone" header="Zona afectada" /><Column header="Indicación al cliente" body={row => row.message === 'Margen de' && row.minutes ? `Margen de ${row.minutes} minutos` : row.message} /><Column field="agent" header="Registró" /><Column header="Cierre" body={row => row.status === 'NORMALIZADO' ? <>{row.resolution_note || 'Sin detalle'}<small className="delay-close-meta">{row.normalized_by || '—'} · {formatDate(row.normalized_at)}</small></> : '—'} /><Column header="Opciones" body={row => <RowMenu id={`delay-${row.id}`} label={`Opciones de la demora en ${row.zone}`} items={actionItems(row)} />} frozen alignFrozen="right" />
    </DataTable></Card>
    <Dialog header={title} visible={Boolean(dialog)} onHide={close} modal appendTo={document.body} maskClassName="tw-z-[1100]" className="tw-overflow-visible" contentClassName="tw-overflow-visible" style={{ width: 'min(640px, 95vw)' }} breakpoints={{ '640px': '95vw' }}><form onSubmit={save} className="tw-flex tw-flex-col tw-gap-3">
      {dialog?.row && dialog.kind !== 'create' && <div className="tw-grid tw-gap-1"><strong>{dialog.row.department} · {dialog.row.zone}</strong><span>{dialog.row.service}</span><small>{dialog.row.message}</small></div>}
      {dialog?.kind === 'create' && <div className="tw-grid tw-grid-cols-1 tw-gap-3 md:tw-grid-cols-2"><Field label="Prestación afectada"><Dropdown appendTo={document.body} panelClassName="[&.p-dropdown-panel]:tw-z-[1200]" className="tw-h-9" value={form.service} options={options(delayServices)} onChange={event => update('service', event.value)} /></Field><Field label="Departamento"><Dropdown appendTo={document.body} panelClassName="[&.p-dropdown-panel]:tw-z-[1200]" className="tw-h-9" value={form.department} options={model.departmentOptions.slice(1)} onChange={event => update('department', event.value)} filter /></Field><Field label="Zona afectada" wide><InputTextarea value={form.zone} onChange={event => update('zone', event.target.value)} rows={3} required /></Field><Field label="Indicación al cliente"><Dropdown appendTo={document.body} panelClassName="[&.p-dropdown-panel]:tw-z-[1200]" className="tw-h-9" value={form.message} options={options(delayMessages)} onChange={event => update('message', event.value)} /></Field>{form.message === 'Margen de' && <Field label="Margen en minutos"><InputNumber value={form.minutes} onValueChange={event => update('minutes', event.value)} min={1} max={1440} /></Field>}<Field label="Volver a verificar en"><Dropdown appendTo={document.body} panelClassName="[&.p-dropdown-panel]:tw-z-[1200]" className="tw-h-9" value={form.review_minutes} options={reviewOptions} onChange={event => update('review_minutes', event.value)} /></Field></div>}
      {dialog?.kind === 'verify' && <><Field label="¿Cómo se verificó que continúa vigente?"><InputTextarea value={form.verification_note || ''} onChange={event => update('verification_note', event.target.value)} rows={4} required /></Field><Field label="Volver a revisar en"><Dropdown appendTo={document.body} panelClassName="[&.p-dropdown-panel]:tw-z-[1200]" className="tw-h-9" value={form.review_minutes} options={reviewOptions} onChange={event => update('review_minutes', event.value)} /></Field></>}
      {dialog?.kind === 'normalize' && <Field label="¿Cómo se confirmó la normalización?"><InputTextarea value={form.resolution_note || ''} onChange={event => update('resolution_note', event.target.value)} rows={5} required /></Field>}
      {dialog?.kind === 'history' && <div className="notice-timeline">{events.length ? events.map((entry, index) => <article key={entry.id || index}><strong>{statusNames[entry.event_type] || entry.event_type}</strong><time>{formatDate(entry.created_at)}</time><span>{entry.actor}</span>{entry.note && <p>{entry.note}</p>}{entry.review_due_at && <small>Próxima revisión: {formatDate(entry.review_due_at)}</small>}</article>) : <p>No hay eventos registrados.</p>}</div>}
      <div className="tw-flex tw-justify-end tw-gap-2"><Button className="tw-h-9" type="button" label={dialog?.kind === 'history' ? 'Cerrar' : 'Cancelar'} text onClick={close} disabled={busy} />{dialog?.kind !== 'history' && <Button className="tw-h-9" type="submit" label={busy ? 'Guardando…' : dialog?.kind === 'normalize' ? 'Confirmar cierre' : dialog?.kind === 'verify' ? 'Renovar vigencia' : 'Guardar'} loading={busy} disabled={busy} />}</div>
    </form></Dialog>
  </div>;
}

export function NoticesView({ model }) {
  const [filters, setFilters] = useState(model.filters);
  const [appliedFilters, setAppliedFilters] = useState(model.filters);
  const [view, setView] = useState(model.activeView);
  const [page, setPage] = useState(model.page);
  const requestSequence = useRef(0);
  const [dialog, setDialog] = useState(null);
  const [form, setForm] = useState(noticeBlank);
  const [events, setEvents] = useState([]);
  const [assignees, setAssignees] = useState([]);
  const [duplicate, setDuplicate] = useState(null);
  const load = async (nextFilters = appliedFilters, nextView = view, nextOffset = 0, nextLimit = page.limit || 50) => {
    const sequence = ++requestSequence.current;
    const query = new URLSearchParams();
    for (const [name, value] of Object.entries({ date_from: nextFilters.from, date_to: nextFilters.to, status: nextFilters.status, task: nextFilters.task, contact: nextFilters.contact, q: nextFilters.search, scope: nextView, offset: nextOffset, limit: nextLimit })) if (value !== '' && value != null) query.set(name, value);
    const response = await model.request(`/api/notices/page?${query}`);
    if (response.offset > 0 && response.offset >= response.total) return load(nextFilters, nextView, Math.max(0, Math.floor((response.total - 1) / nextLimit) * nextLimit), nextLimit);
    if (sequence === requestSequence.current) setPage(response);
    return response;
  };
  const { toast, busy, run, notify } = useOperation({ ...model, refresh: () => load(appliedFilters, view, page.offset, page.limit) });
  const apply = nextFilters => { setAppliedFilters({ ...nextFilters }); model.onStateChange?.(nextFilters, view); load(nextFilters, view).catch(error => notify('error', 'No se pudieron aplicar los filtros', errorText(error))); };
  const clear = () => { const empty = { from: '', to: '', status: '', task: '', contact: '', search: '' }; setFilters(empty); setAppliedFilters(empty); model.onStateChange?.(empty, view); load(empty, view).catch(error => notify('error', 'No se pudieron limpiar los filtros', errorText(error))); };
  const selectView = value => { const next = value === 'resolved' ? { ...appliedFilters, status: '' } : appliedFilters; if (next !== appliedFilters) { setFilters(next); setAppliedFilters(next); } setView(value); model.onStateChange?.(next, value, page.limit); load(next, value).catch(error => notify('error', 'No se pudo cambiar la vista', errorText(error))); };
  const findExisting = row => { const next = { ...appliedFilters, search: row.task_number || row.phone || '' }; setFilters(next); setAppliedFilters(next); setView('open'); model.onStateChange?.(next, 'open'); load(next, 'open').catch(error => notify('error', 'No se pudo buscar el aviso', errorText(error))); };
  const rows = page.items;
  const metricCounts = page.counts;
  const showComments = view === 'resolved';
  const update = (key, value) => { setForm(current => ({ ...current, [key]: value })); if (dialog?.kind === 'create') setDuplicate(null); };
  const close = () => { setDialog(null); setForm(noticeBlank); setEvents([]); setDuplicate(null); };
  const open = (kind, row = null, status = 'RESUELTO') => { setForm({ ...noticeBlank, comments: row?.comments || '', managed_by: row?.managed_by || '', status }); setDialog({ kind, row }); };
  const assign = async row => { try { setAssignees(await model.request('/api/notices/assignees')); open('assign', row); } catch (error) { notify('error', 'No se pudieron cargar responsables', errorText(error)); } };
  const history = async row => { try { setEvents(await model.request(`/api/notices/${row.id}/history`)); open('history', row); } catch (error) { notify('error', 'No se pudo cargar el historial', errorText(error)); } };
  const save = async event => {
    event.preventDefault();
    const { kind, row } = dialog;
    if (kind === 'create') {
      if (!form.notice_type || form.detail.trim().length < 2) { notify('error', 'Faltan datos', 'Seleccioná un motivo y escribí el detalle.'); return; }
      const body = { task_number: form.task_number.trim() || null, phone: form.phone.trim() || null, notice_type: form.notice_type, audience: form.audience, detail: form.detail.trim(), communicated_by: model.currentUser, status: 'PENDIENTE', managed_by: form.managed_by ? model.currentUser : null };
      if (!duplicate) {
        try { const matches = await model.request(`/api/notices/duplicates?${new URLSearchParams({ task_number: body.task_number || '', phone: body.phone || '', notice_type: body.notice_type })}`); if (matches.length) { setDuplicate(matches[0]); return; } }
        catch (error) { notify('error', 'No se pudo verificar el aviso', errorText(error)); return; }
      }
      run(() => model.request('/api/notices', { method: 'POST', body: JSON.stringify({ ...body, allow_duplicate: Boolean(duplicate) }) }), 'Aviso registrado', close);
    } else if (kind === 'comment') run(() => model.request(`/api/notices/${row.id}/status`, { method: 'PATCH', body: JSON.stringify({ status: row.status, actor: model.currentUser, managed_by: row.managed_by || null, comments: form.comments || null }) }), 'Comentario guardado', close);
    else if (kind === 'assign') run(() => model.request(`/api/notices/${row.id}/status`, { method: 'PATCH', body: JSON.stringify({ managed_by: form.managed_by || null }) }), 'Responsable actualizado', close);
    else if (kind === 'close') {
      if ((form.comments || '').trim().length < 2) { notify('error', 'Faltan datos', 'Indicá el resultado o motivo del cierre.'); return; }
      run(() => model.request(`/api/notices/${row.id}/status`, { method: 'PATCH', body: JSON.stringify({ status: form.status, comments: form.comments.trim() }) }), form.status === 'RESUELTO' ? 'Aviso resuelto' : 'Aviso cancelado', close);
    }
  };
  const changeStatus = (row, status) => {
    if (['RESUELTO', 'CANCELADO'].includes(status)) return open('close', row, status);
    run(() => model.request(`/api/notices/${row.id}/status`, { method: 'PATCH', body: JSON.stringify({ status, ...(!row.managed_by && model.canAssign ? { managed_by: model.currentUser } : {}) }) }), `Estado: ${statusNames[status]}`);
  };
  const actions = row => [
    { label: 'Ver aviso completo', icon: 'pi pi-eye', command: () => open('detail', row) },
    ...(model.canAssign ? [{ label: row.managed_by ? 'Reasignar' : 'Asignar', icon: 'pi pi-user-plus', command: () => assign(row) }] : []),
    ...(model.canComment ? [{ label: 'Editar seguimiento', icon: 'pi pi-pencil', command: () => open('comment', row) }] : []),
    { label: 'Historial', icon: 'pi pi-history', command: () => history(row) }
  ];
  const statusOptions = [
    ...(model.canChangeStatus ? ['PENDIENTE', 'EN_GESTION', 'ESPERANDO_RESPUESTA'] : []),
    ...(model.canClose ? ['RESUELTO', 'CANCELADO'] : [])
  ].map(status => ({ label: statusNames[status], value: status }));
  const title = { create: 'Registrar nuevo aviso', comment: 'Editar seguimiento', assign: 'Asignar aviso', close: 'Cerrar aviso', history: 'Historial del aviso', detail: 'Aviso completo' }[dialog?.kind];
  const changeFilter = (key, value) => setFilters(current => ({ ...current, [key]: value }));
  return <div className="operational-view notice-prime-view tw-flex tw-min-w-0 tw-flex-col tw-gap-3 tw-text-[13px]">
    <Toast ref={toast} />
    <section className="tw-grid tw-grid-cols-1 tw-gap-3 sm:tw-grid-cols-2 xl:tw-grid-cols-4" aria-label="Indicadores de avisos">{model.metrics.map(metric => <Card key={metric.value} className={`notice-prime-metric tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm ${metric.tone} ${view === metric.value ? 'tw-ring-2 tw-ring-blue-500 tw-bg-[var(--color-primary-bg)]' : ''}`} pt={{ body: { className: 'tw-p-0' }, content: { className: 'tw-p-0' } }}><button type="button" className={`tw-grid tw-w-full tw-gap-1 tw-border-0 tw-border-l-[3px] tw-border-solid tw-bg-transparent tw-p-3 tw-text-left tw-text-[var(--text)] [&>span]:tw-text-xs [&>span]:tw-text-[var(--text-muted)] [&>strong]:tw-text-2xl [&>small]:tw-text-xs [&>small]:tw-text-[var(--text-muted)] ${metric.tone === 'urgent' ? 'tw-border-[var(--color-urgente)]' : metric.tone === 'mine' ? 'tw-border-[var(--color-ok)]' : metric.tone === 'waiting' ? 'tw-border-[var(--color-espera)]' : 'tw-border-slate-400'}`} onClick={() => selectView(metric.value)} aria-pressed={view === metric.value}><span>{metric.label}</span><strong>{metricCounts[metric.value]}</strong><small>{metric.help}</small></button></Card>)}</section>
    <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-2"><strong>{page.total} avisos</strong><div className="tw-flex tw-flex-wrap tw-gap-2">{model.canExport && <Button className="tw-h-9" label="Descargar esta vista" icon="pi pi-download" size="small" outlined onClick={model.onExport} />}{model.canCreate && <Button className="tw-h-9" label="Nuevo aviso" icon="pi pi-plus" size="small" onClick={() => open('create')} />}</div></div>
    <Card className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-3' } }}><div className="tw-flex tw-flex-wrap tw-items-end tw-gap-4"><Field label="Vista"><Dropdown appendTo={document.body} className="tw-h-9" value={view} options={model.viewOptions} onChange={event => selectView(event.value)} /></Field><Field label="Desde"><Calendar appendTo={document.body} className="tw-h-9" value={asDate(filters.from)} onChange={event => changeFilter('from', dateString(event.value))} dateFormat="dd/mm/yy" showIcon /></Field><Field label="Hasta"><Calendar appendTo={document.body} className="tw-h-9" value={asDate(filters.to)} onChange={event => changeFilter('to', dateString(event.value))} dateFormat="dd/mm/yy" showIcon /></Field><Field label="Estado"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.status} options={model.statusOptions} onChange={event => changeFilter('status', event.value)} /></Field><Field label="Tarea"><InputText className="tw-h-9" value={filters.task} onChange={event => changeFilter('task', event.target.value)} onKeyDown={event => event.key === 'Enter' && apply(filters)} /></Field><Field label="Teléfono o contacto"><InputText className="tw-h-9" value={filters.contact} onChange={event => changeFilter('contact', event.target.value)} onKeyDown={event => event.key === 'Enter' && apply(filters)} /></Field><Field label="Búsqueda"><InputText className="tw-h-9" value={filters.search} onChange={event => changeFilter('search', event.target.value)} onKeyDown={event => event.key === 'Enter' && apply(filters)} /></Field><Button className="tw-h-9" label="Aplicar filtros" size="small" outlined onClick={() => apply(filters)} /><Button className="tw-h-9" label="Limpiar" size="small" text onClick={clear} /></div></Card>
    <Card className="notice-prime-table-card tw-min-w-0 tw-max-w-full tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-0' }, content: { className: 'tw-p-0' } }}><DataTable stripedRows value={rows} dataKey="id" size="small" className={`notice-prime-table tw-min-w-0 [&_.p-datatable-wrapper]:tw-overflow-x-hidden max-sm:[&_.p-datatable-thead]:tw-hidden max-sm:[&_.p-datatable-tbody>tr]:tw-grid max-sm:[&_.p-datatable-tbody>tr]:tw-grid-cols-2 max-sm:[&_.p-datatable-tbody>tr>td]:tw-w-full max-sm:[&_.p-datatable-tbody>tr>td:nth-child(3)]:tw-col-span-2 ${showComments ? 'max-sm:[&_.p-datatable-tbody>tr>td:nth-child(6)]:tw-col-span-2 max-sm:[&_.p-datatable-tbody>tr>td:nth-child(7)]:tw-col-span-2' : 'max-sm:[&_.p-datatable-tbody>tr>td:nth-child(6)]:tw-col-span-2'}`} tableClassName="notice-table tw-table-fixed tw-w-full" emptyMessage="No hay avisos para esos filtros" aria-label="Avisos del equipo" lazy paginator rows={page.limit || 50} first={page.offset} totalRecords={page.total} onPage={event => { const offset = event.rows === page.limit ? event.first : 0; model.onStateChange?.(appliedFilters, view, event.rows); load(appliedFilters, view, offset, event.rows).catch(error => notify('error', 'No se pudo cambiar de página', errorText(error))); }} onRowClick={event => open('detail', event.data)} rowClassName={() => 'tw-cursor-pointer'}>
      <Column header="Tiempo" style={{ width: showComments ? '11%' : '13%' }} body={row => <div className="tw-flex tw-min-w-0 tw-flex-col tw-gap-1"><span className="tw-whitespace-nowrap">{formatNoticeTime(row.created_at)}</span><span className="tw-text-xs tw-text-slate-500">Hace {model.age(row).replace(/\s+/g, '')}</span></div>} />
      <Column header="Tarea" style={{ width: showComments ? '13%' : '15%' }} body={row => <div className="tw-flex tw-min-w-0 tw-flex-col tw-gap-1 tw-break-words">{row.task_number ? <a className="tw-font-semibold tw-text-blue-600 tw-break-words" href={`https://aps.portoservicios.uy/3/tareas/${encodeURIComponent(row.task_number)}`} target="_blank" rel="noopener noreferrer" onClick={event => event.stopPropagation()}>{row.task_number}</a> : <span>Sin tarea</span>}<span className="tw-text-xs tw-break-words">{row.phone || 'Sin teléfono'}</span></div>} />
      <Column header="Motivo y resumen" style={{ width: showComments ? '24%' : '32%' }} body={row => <div className="tw-flex tw-w-full tw-min-w-0 tw-flex-col tw-gap-1"><strong className="tw-whitespace-normal tw-break-words tw-font-semibold">{row.notice_type}</strong><span className="tw-block tw-w-full tw-min-w-0 tw-truncate tw-text-slate-500" title={row.detail}>{row.detail}</span></div>} />
      <Column header="Responsable" style={{ width: showComments ? '15%' : '18%' }} body={row => <div className="tw-flex tw-flex-col tw-items-start tw-justify-center tw-gap-1 tw-w-full tw-min-w-0 tw-whitespace-normal tw-break-words">{row.managed_by ? <span className="tw-font-medium tw-whitespace-normal tw-break-words">{row.managed_by}</span> : model.canAssign && !noticeIsClosed(row) ? <Button className="tw-h-9 tw-whitespace-nowrap tw-max-w-full" label="Asignarme" size="small" onClick={event => { event.stopPropagation(); run(() => model.request(`/api/notices/${row.id}/status`, { method: 'PATCH', body: JSON.stringify({ managed_by: model.currentUser }) }), 'Aviso asignado'); }} /> : <span className="tw-text-slate-500">Sin responsable</span>}</div>} />
      <Column header="Estado" style={{ width: showComments ? '14%' : '15%' }} body={row => <div onClick={event => event.stopPropagation()}>{statusOptions.length ? <Dropdown appendTo={document.body} className="tw-w-full tw-min-w-0" aria-label={`Estado del aviso ${row.task_number || row.id}`} value={row.status} options={statusOptions} onChange={event => changeStatus(row, event.value)} valueTemplate={() => <Tag value={noticeState(row).label} severity={noticeState(row).severity} className="tw-whitespace-normal tw-text-center tw-text-xs" />} itemTemplate={option => <Tag value={option.label} severity={noticeStatusDisplay[option.value]?.severity || 'secondary'} className="tw-text-xs" />} /> : <Tag value={noticeState(row).label} severity={noticeState(row).severity} className="tw-whitespace-normal tw-text-center tw-text-xs" />}</div>} />
      {showComments && <Column header="Comentarios" style={{ width: '16%' }} body={row => <span className="tw-whitespace-normal tw-break-words">{row.comments || 'Sin comentario de cierre'}</span>} />}
      <Column header="Acciones" style={{ width: '7%' }} body={row => <div onClick={event => event.stopPropagation()}><RowMenu id={`notice-actions-${row.id}`} label={`Acciones del aviso ${row.task_number || row.id}`} items={actions(row)} /></div>} />
    </DataTable></Card>
    <Dialog header={title} visible={Boolean(dialog)} onHide={close} modal appendTo={document.body} style={{ width: 'min(640px, 95vw)' }}><form onSubmit={save} className="tw-flex tw-flex-col tw-gap-4">
      {dialog?.kind === 'create' && <div className="tw-grid tw-grid-cols-1 tw-gap-3 md:tw-grid-cols-2"><Field label="Número de tarea"><InputText className="tw-h-9" value={form.task_number} onChange={event => update('task_number', event.target.value)} maxLength={120} /></Field><Field label="Teléfono del cliente"><InputText className="tw-h-9" value={form.phone} onChange={event => update('phone', event.target.value)} maxLength={80} /></Field><Field label="Motivo"><Dropdown appendTo={document.body} className="tw-h-9" value={form.notice_type} options={options(noticeTypes)} onChange={event => { update('notice_type', event.value); setDuplicate(null); }} placeholder="Seleccionar motivo" /></Field><Field label="Dirigido a"><Dropdown appendTo={document.body} className="tw-h-9" value={form.audience} options={[{ label: 'Todo el equipo', value: 'TODOS' }, { label: 'Telefonistas', value: 'TELEFONISTAS' }, { label: 'Planificadores', value: 'PLANIFICADORES' }]} onChange={event => update('audience', event.value)} /></Field><Field label="¿Qué necesita saber o hacer el equipo?" wide><InputTextarea value={form.detail} onChange={event => update('detail', event.target.value)} rows={6} maxLength={4000} required /></Field>{model.canAssign && <label className="tw-flex tw-items-center tw-gap-2"><input type="checkbox" checked={Boolean(form.managed_by)} onChange={event => update('managed_by', event.target.checked)} />Asignármelo al guardar</label>}</div>}
      {duplicate && dialog?.kind === 'create' && <div className="tw-rounded-md tw-border tw-border-amber-300 tw-bg-amber-50 tw-p-3"><strong>Posible aviso duplicado</strong><p>{duplicate.duplicate_reason}</p><p>Tarea: {duplicate.task_number || 'Sin tarea'} · Estado: {statusNames[duplicate.status] || duplicate.status}</p><Button className="tw-h-9" type="button" label="Ver aviso existente" text onClick={() => { close(); findExisting(duplicate); }} /><small>Si es otro caso, guardalo como caso independiente.</small></div>}
      {dialog?.kind === 'comment' && <Field label="Comentario de seguimiento"><InputTextarea value={form.comments || ''} onChange={event => update('comments', event.target.value)} rows={7} /></Field>}
      {dialog?.kind === 'assign' && <Field label="Responsable"><Dropdown appendTo={document.body} className="tw-h-9" value={form.managed_by} options={[{ label: 'Sin responsable', value: '' }, ...assignees.map(person => ({ label: `${person.display_name} · ${person.role_name}`, value: person.display_name }))]} onChange={event => update('managed_by', event.value)} filter /></Field>}
      {dialog?.kind === 'close' && <><Field label="Resultado"><Dropdown appendTo={document.body} className="tw-h-9" value={form.status} options={[{ label: 'Resuelto', value: 'RESUELTO' }, { label: 'Cancelado', value: 'CANCELADO' }]} onChange={event => update('status', event.value)} /></Field><Field label="Resultado o motivo del cierre"><InputTextarea value={form.comments || ''} onChange={event => update('comments', event.target.value)} rows={6} maxLength={4000} required /></Field></>}
      {dialog?.kind === 'history' && <div className="notice-timeline">{events.length ? events.map((entry, index) => <article key={entry.id || index}><strong>{entry.event_type}</strong><time>{formatDate(entry.created_at)}</time><span>{entry.actor}</span>{entry.comment && <p>{entry.comment}</p>}{entry.detail && <small>{entry.detail}</small>}</article>) : <p>No hay movimientos registrados.</p>}</div>}
      {dialog?.kind === 'detail' && <div className="tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]"><div className="tw-flex tw-flex-wrap tw-items-center tw-gap-3"><Tag value={noticeState(dialog.row).label} severity={noticeState(dialog.row).severity} /><strong>{dialog.row.notice_type}</strong></div><div className="tw-grid tw-grid-cols-1 tw-gap-3 sm:tw-grid-cols-2">{[['Registrado', formatDate(dialog.row.created_at)], ['Tarea', dialog.row.task_number || 'Sin tarea'], ['Teléfono', dialog.row.phone || 'Sin teléfono'], ['Responsable', dialog.row.managed_by || 'Sin responsable'], ['Destinatario', dialog.row.audience || '—'], ['Dio aviso', dialog.row.communicated_by || '—']].map(([label, value]) => <div key={label} className="tw-flex tw-min-w-0 tw-flex-col tw-gap-1"><span className="tw-text-xs tw-text-slate-500">{label}</span><span className="tw-whitespace-normal tw-break-words">{value}</span></div>)}</div><div className="tw-flex tw-min-w-0 tw-flex-col tw-gap-1"><span className="tw-text-xs tw-text-slate-500">Detalle completo</span><p className="tw-m-0 tw-whitespace-pre-wrap tw-break-words">{dialog.row.detail || '—'}</p></div><div className="tw-flex tw-min-w-0 tw-flex-col tw-gap-1"><span className="tw-text-xs tw-text-slate-500">Comentarios</span><p className="tw-m-0 tw-whitespace-pre-wrap tw-break-words">{dialog.row.comments || 'Sin comentarios'}</p></div></div>}
      <div className="tw-flex tw-justify-end tw-gap-2"><Button className="tw-h-9" type="button" label={['history', 'detail'].includes(dialog?.kind) ? 'Cerrar' : 'Cancelar'} text onClick={close} disabled={busy} />{!['history', 'detail'].includes(dialog?.kind) && <Button className="tw-h-9" type="submit" label={busy ? 'Guardando…' : 'Guardar'} loading={busy} disabled={busy} />}</div>
    </form></Dialog>
  </div>;
}
