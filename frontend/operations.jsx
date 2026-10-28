import React, { useEffect, useRef, useState } from 'react';
import { addLocale } from 'primereact/api';
import { Button } from 'primereact/button';
import { Calendar } from 'primereact/calendar';
import { Card } from 'primereact/card';
import { Column } from 'primereact/column';
import { DataTable } from './dense-table.jsx';
import { formatDateTime } from './date-format.js';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Menu } from 'primereact/menu';
import { MultiSelect } from 'primereact/multiselect';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { displayLocation, displayService } from './operational-labels.js';

const statusNames = { PENDIENTE: 'Pendiente', EN_GESTION: 'En gestión', ESPERANDO_RESPUESTA: 'Esperando respuesta', RESUELTO: 'Resuelto', CANCELADO: 'Cancelado', NORMALIZADO: 'Normalizado' };
const noticeTypes = ['Volverán a llamar', 'Reclama no cumplimiento', 'Se envió HSM', 'Solicita coordinación', 'Solicita información', 'Reclamo por demora', 'Otro motivo'];
const delayServices = ['TODAS', 'GRÚA', 'ML', 'SINIESTROS'];
const delayMessages = ['No confirmar tiempos', 'A confirmar', 'Margen de', 'Máximo de', 'Intervalo estimado', 'No generar servicio'];
const reviewOptions = [30, 60, 120, 240, 480, 1440].map(value => ({ value, label: value < 60 ? `${value} min` : `${value / 60} h` }));
const durationOptions = [{ label: '30 min', value: 30 }, { label: '1 hora', value: 60 }, { label: '2 horas', value: 120 }, { label: '4 horas', value: 240 }, { label: 'Sin definir', value: null }];
const delayBlank = { service: null, department: null, zone: 'Todo el departamento', message: 'No confirmar tiempos', minutes: null, minutes_min: null, minutes_max: null, instruction_text: '', duration_minutes: null, review_minutes: 120 };
const noticeBlank = { task_number: '', phone: '', notice_type: '', audience: 'TODOS', detail: '', managed_by: false };
const options = (values, display = value => value) => values.map(value => ({ label: display(value), value }));
const asDate = value => value ? new Date(`${value}T12:00:00`) : null;
const dateString = value => value ? `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}` : '';
const formatDate = formatDateTime;
const formatNoticeTime = formatDateTime;
const delayIndication = row => {
  const value = row.message === 'Margen de' ? `Margen: ${row.minutes} min`
    : row.message === 'Máximo de' ? `Máximo: ${row.minutes} min`
    : row.message === 'Intervalo estimado' ? `Entre ${row.minutes_min} y ${row.minutes_max} min`
    : row.message === 'Otra indicación' ? row.instruction_text || 'Otra indicación'
    : row.message;
  return <span>{value}{row.status === 'VIGENTE' && row.needs_review && <small className="tw-ml-2 tw-text-amber-700">· Revisar vigencia</small>}</span>;
};
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
addLocale('es', {
  firstDayOfWeek: 1,
  dayNames: ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'],
  dayNamesShort: ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'],
  dayNamesMin: ['DO', 'LU', 'MA', 'MI', 'JU', 'VI', 'SA'],
  monthNames: ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'],
  monthNamesShort: ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'],
  today: 'Hoy',
  clear: 'Limpiar',
  dateFormat: 'dd/mm/yy'
});
const noticeDropdownPt = { input: { className: 'tw-text-[13px]' }, item: { className: 'tw-text-[13px] tw-border-b tw-border-[var(--border)] hover:tw-bg-[var(--surface-muted)] last:tw-border-b-0' } };
const noticeViewDropdownPt = {
  root: { className: 'tw-flex tw-items-center' },
  input: { className: 'tw-flex tw-h-full tw-min-w-0 tw-items-center tw-px-3 tw-py-0 tw-text-[13px]' },
  item: { className: 'tw-m-0 tw-flex tw-w-full tw-box-border tw-items-center tw-rounded-sm tw-px-3 tw-py-2 tw-text-[13px]' }
};
const noticeRowDropdownPt = { input: { className: 'tw-px-2 tw-py-1 tw-text-[13px]' }, item: { className: 'tw-px-2 tw-py-1 tw-text-[13px] tw-border-b tw-border-[var(--border)] hover:tw-bg-[var(--surface-muted)] last:tw-border-b-0' } };
const noticeCalendarPanel = 'notice-calendar-panel tw-w-[320px] tw-max-w-[calc(100vw-24px)]';
const errorText = error => error?.message || 'No se pudo completar la operación';

function Field({ label, children, wide = false, className = '' }) {
  const generatedId = React.useId();
  const fieldId = children?.props?.id || children?.props?.inputId || generatedId;
  const nativeInput = children?.type === InputText || children?.type === InputTextarea || typeof children?.type === 'string';
  const control = React.isValidElement(children) ? React.cloneElement(children, {
    [nativeInput ? 'id' : 'inputId']: fieldId,
    'aria-label': children.props['aria-label'] || label
  }) : children;
  return <label htmlFor={fieldId} className={`tw-flex tw-min-w-0 tw-flex-col tw-gap-1 tw-text-xs tw-font-medium ${wide ? 'md:tw-col-span-2' : ''} ${className}`}><span>{label}</span>{control}</label>;
}

function DelayCreateFields({ form, setForm, update, model }) {
  const chosenZones = form.zone === 'Todo el departamento' ? [] : form.zone.split(',').map(zone => zone.trim()).filter(Boolean);
  const zoneChoices = (model.geography[form.department] || []).filter(zone => zone !== 'Todo el departamento');
  return <div className="tw-grid tw-grid-cols-1 tw-gap-3 md:tw-grid-cols-2">
    <Field label="Prestación afectada"><Dropdown appendTo={document.body} panelClassName="tw-z-[1200]" className="tw-h-9" value={form.service} options={options(delayServices, displayService)} onChange={event => setForm(current => ({ ...current, service: event.value, department: null, zone: 'Todo el departamento' }))} placeholder="Seleccionar prestación" /></Field>
    <Field label="Departamento"><Dropdown appendTo={document.body} panelClassName="tw-z-[1200]" className="tw-h-9" value={form.department} options={model.departmentOptions.slice(1)} onChange={event => setForm(current => ({ ...current, department: event.value, zone: 'Todo el departamento' }))} placeholder="Seleccionar departamento" disabled={!form.service} filter /></Field>
    <div className="tw-flex tw-min-w-0 tw-flex-col tw-gap-1 md:tw-col-span-2"><span className="tw-text-xs tw-font-medium">Zonas afectadas</span><MultiSelect appendTo={document.body} panelClassName="tw-z-[1200]" className="tw-w-full" aria-label="Zonas afectadas" value={chosenZones} options={options(zoneChoices, displayLocation)} onChange={event => update('zone', event.value.length ? event.value.join(', ') : 'Todo el departamento')} placeholder="Todo el departamento" disabled={!form.department} filter display="chip" maxSelectedLabels={3} /><Button type="button" label="Todo el departamento" size="small" text className="tw-self-start" onClick={() => update('zone', 'Todo el departamento')} disabled={!form.department} /></div>
    <Field label="Tiempo / indicación"><Dropdown appendTo={document.body} panelClassName="tw-z-[1200]" className="tw-h-9" value={form.message} options={options(delayMessages)} onChange={event => setForm(current => ({ ...current, message: event.value, minutes: null, minutes_min: null, minutes_max: null, instruction_text: '' }))} /></Field>
    {['Margen de', 'Máximo de'].includes(form.message) && <Field label={form.message === 'Margen de' ? 'Margen informado en minutos' : 'Máximo informado en minutos'}><InputNumber value={form.minutes} onValueChange={event => update('minutes', event.value)} min={1} max={1440} /></Field>}
    {form.message === 'Intervalo estimado' && <><Field label="Desde (minutos)"><InputNumber value={form.minutes_min} onValueChange={event => update('minutes_min', event.value)} min={1} max={1440} /></Field><Field label="Hasta (minutos)"><InputNumber value={form.minutes_max} onValueChange={event => update('minutes_max', event.value)} min={1} max={1440} /></Field></>}
    {form.message === 'Margen de' && <small className="md:tw-col-span-2">Este margen no se suma al estándar ni representa un tiempo total de llegada.</small>}
    <div className="md:tw-col-span-2"><span className="tw-mb-1 tw-block tw-text-xs tw-font-medium">Duración estimada</span><div className="tw-flex tw-flex-wrap tw-items-center tw-gap-3 tw-w-full">{durationOptions.map(option => <Button key={option.label} type="button" size="small" label={option.label} outlined={form.duration_minutes !== option.value} onClick={() => setForm(current => ({ ...current, duration_minutes: option.value, review_minutes: option.value || 120 }))} />)}</div><small className="tw-mt-1 tw-block tw-text-[var(--text-muted)]">{form.duration_minutes ? `Próximo control en ${form.duration_minutes} min` : 'Sin duración definida: próximo control en 2 horas'}</small></div>
  </div>;
}

let activeRowMenu = null;

function RowMenu({ id, items, label, text, onBeforeToggle }) {
  const menu = useRef(null);
  useEffect(() => () => { if (activeRowMenu?.id === id) { menu.current?.hide({ currentTarget: document.body }); activeRowMenu = null; } }, [id]);
  const toggle = event => {
    event.stopPropagation();
    onBeforeToggle?.();
    if (activeRowMenu?.id === id) { menu.current?.hide(event); activeRowMenu = null; return; }
    activeRowMenu?.menu?.current?.hide(event);
    menu.current?.show(event);
    activeRowMenu = { id, menu };
  };
  return <><Menu ref={menu} id={`row-menu-${id}`} model={items} popup={true} appendTo={document.body} onHide={() => { if (activeRowMenu?.id === id) activeRowMenu = null; }} /><Button className="tw-h-9" type="button" icon="pi pi-ellipsis-v" label={text} text rounded={!text} size="small" aria-label={label} aria-haspopup="menu" aria-controls={`row-menu-${id}`} onClick={toggle} /></>;
}

function NoticeStatusDropdown({ row, statusOptions, dropdownRefs, closeOtherStatusDropdowns, closeNoticeMenu, changeStatus }) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  return <Dropdown
    ref={dropdown => { if (dropdown) dropdownRefs.current.set(row.id, dropdown); else dropdownRefs.current.delete(row.id); }}
    appendTo={document.body}
    scrollHeight="264px"
    pt={noticeRowDropdownPt}
    className={`notice-status-dropdown tw-w-full tw-min-w-0 tw-transition-none ${isDropdownOpen
      ? 'tw-border-blue-500 tw-bg-slate-50 tw-ring-2 tw-ring-blue-500/40 dark:tw-border-blue-400 dark:tw-bg-slate-800 dark:tw-ring-blue-400/60'
      : 'tw-border-gray-300'}`}
    aria-label={`Estado del aviso ${row.task_number || row.id}`}
    value={row.status}
    options={statusOptions}
    onClick={event => { closeOtherStatusDropdowns(row.id); closeNoticeMenu(event); setIsDropdownOpen(true); }}
    onShow={() => { closeOtherStatusDropdowns(row.id); closeNoticeMenu(); setIsDropdownOpen(true); }}
    onHide={() => setIsDropdownOpen(false)}
    onKeyDown={event => { if (event.key === 'Escape') setIsDropdownOpen(false); }}
    onChange={event => changeStatus(row, event.value)}
    valueTemplate={() => <Tag value={noticeState(row).label} severity={noticeState(row).severity} className="tw-whitespace-nowrap tw-text-center tw-text-[13px] tw-px-2 tw-py-1" />}
    itemTemplate={option => <Tag value={option.label} severity={noticeStatusDisplay[option.value]?.severity || 'secondary'} className="tw-text-[13px] tw-px-2 tw-py-1" />}
  />;
}

function useOperation(model) {
  const toast = useRef(null);
  const [busy, setBusy] = useState(false);
  const notify = (severity, summary, detail) => toast.current?.show({ severity, summary, detail, life: severity === 'error' ? 5500 : 3200 });
  const run = async (task, success, after, onConflict) => {
    if (busy) return false;
    setBusy(true);
    try {
      await task();
      notify('success', success);
      window.toast?.(success);
      after?.();
    } catch (error) {
      if(error.stale){setBusy(false);return false;}
      notify('error', 'No se pudo guardar', errorText(error));
      if(error.status===409){await model.refresh().catch(()=>{});await onConflict?.(error);}
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
  const root = useRef(null);
  const normalizing = useRef(new Set());
  const pageSequence = useRef(0);
  const filterTransition = useRef(false);
  useEffect(() => () => { pageSequence.current += 1; }, []);
  const [filters, setFilters] = useState(model.filters);
  const [page, setPage] = useState(model.page);
  const [sortField, setSortField] = useState('created_at');
  const [sortOrder, setSortOrder] = useState(-1);
  useEffect(() => setFilters(model.filters), [model.filters]);
  useEffect(() => { pageSequence.current += 1; filterTransition.current=false; setPage(model.page); setSortField('created_at'); setSortOrder(-1); }, [model.page]);
  const [dialog, setDialog] = useState(null);
  const [conflict, setConflict] = useState(false);
  const [form, setForm] = useState(delayBlank);
  const [events, setEvents] = useState([]);
  const { toast, busy, run, notify } = useOperation(model);
  const update = (key, value) => setForm(current => ({ ...current, [key]: value }));
  const close = () => { setDialog(null); setForm(delayBlank); setEvents([]); setConflict(false); };
  const open = (kind, row = null) => { setForm({ ...delayBlank, verification_note: '', resolution_note: '' }); setConflict(false); setDialog({ kind, row }); };
  const history = async row => {
    try { setEvents(await model.request(`/api/delays/${row.id}/events`)); setDialog({ kind: 'history', row }); }
    catch (error) { notify('error', 'No se pudo cargar el historial', errorText(error)); }
  };
  const save = event => {
    event.preventDefault();
    if (conflict) return;
    const { kind, row } = dialog;
    if (kind === 'create') {
      if (!form.service || !form.department || !form.zone || (['Margen de', 'Máximo de'].includes(form.message) && !form.minutes) || (form.message === 'Intervalo estimado' && (!form.minutes_min || !form.minutes_max))) { notify('error', 'Faltan datos', 'Completá prestación, ubicación y los valores de la indicación seleccionada.'); return; }
      run(() => model.request('/api/delays', { method: 'POST', body: JSON.stringify({ ...form, catalog_zone: true, minutes: ['Margen de', 'Máximo de'].includes(form.message) ? form.minutes : null, minutes_min: form.message === 'Intervalo estimado' ? form.minutes_min : null, minutes_max: form.message === 'Intervalo estimado' ? form.minutes_max : null, instruction_text: null, agent: model.currentUser, status: 'VIGENTE' }) }), 'Demora vigente registrada', close);
    } else if (kind === 'verify') {
      if ((form.verification_note || '').trim().length < 2) { notify('error', 'Faltan datos', 'Indicá cómo se verificó la demora.'); return; }
      run(() => model.request(`/api/delays/${row.id}/verify`, { method: 'PATCH', body: JSON.stringify({ expected_revision: row.revision, verification_note: form.verification_note.trim(), review_minutes: form.review_minutes }) }), 'Vigencia renovada y registrada', close, () => setConflict(true));
    }
  };
  const normalize = row => {
    if (normalizing.current.has(row.id)) return;
    normalizing.current.add(row.id);
    run(() => model.request(`/api/delays/${row.id}/normalize`, { method: 'PATCH', body: JSON.stringify({ expected_revision: row.revision }) }),
      'Demora normalizada', null, () => notify('warn', 'La demora cambió', 'Revisá la versión vigente antes de volver a normalizar.'))
      .finally(() => normalizing.current.delete(row.id));
  };
  const changeFilter = (key, value) => setFilters(current => ({ ...current, [key]: value }));
  const finishFilterTransition = task => task.then(result=>{if(!result)filterTransition.current=false;return result;},error=>{filterTransition.current=false;throw error;});
  const applyFilters = () => { pageSequence.current += 1; filterTransition.current=true; return finishFilterTransition(model.onApply(filters)); };
  const clearFilters = () => { pageSequence.current += 1; filterTransition.current=true; return finishFilterTransition(model.onClear()); };
  const loadPage = async (offset, field = sortField, order = sortOrder) => {
    if(filterTransition.current)return;
    const sequence = ++pageSequence.current;
    const active = model.filters;
    const query = new URLSearchParams({ offset: String(offset), limit: '50', sort_by: field, sort_order: order === 1 ? 'asc' : 'desc' });
    const values = { date_from: active.from, date_to: active.to, scope: active.view === 'active' ? 'current' : active.view === 'history' ? 'normalized' : active.view === 'review' ? 'review' : '', department: active.department, service: active.service, q: active.search };
    Object.entries(values).forEach(([name, value]) => { if (value) query.set(name, value); });
    try {
      const result = await model.request(`/api/delays?${query}`);
      if (sequence !== pageSequence.current || root.current?.closest('[hidden]')) return;
      if (offset > 0 && offset >= result.total) { await loadPage(Math.max(0, Math.floor((result.total - 1) / 50) * 50), field, order); return; }
      setPage(result);
    }
    catch (error) { if (sequence === pageSequence.current && !error.stale && !root.current?.closest('[hidden]')) notify('error', 'No se pudo actualizar la tabla', errorText(error)); }
  };
  const changeSort = event => { const field = event.sortField || 'created_at', order = event.sortOrder || -1; setSortField(field); setSortOrder(order); loadPage(0, field, order); };
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && !root.current?.closest('[hidden]')) loadPage(page.offset);
    }, 30000);
    return () => window.clearInterval(timer);
  }, [model.filters, page.offset, sortField, sortOrder]);
  const actionItems = row => [
    ...(row.status === 'VIGENTE' && model.canNormalize ? [
      { label: row.needs_review ? 'Confirmar vigencia' : 'Renovar control', icon: 'pi pi-check', command: () => open('verify', row) },
    ] : []),
    { label: 'Historial', icon: 'pi pi-history', command: () => history(row) }
  ];
  const title = { create: 'Registrar demora vigente', verify: 'Renovar control de vigencia', history: 'Historial de la demora' }[dialog?.kind];
  return <div ref={root} className="operational-view delay-prime-view tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]">
    <Toast ref={toast} />
    <Card className="tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-3' } }}><div className="delay-prime-toolbar tw-flex tw-flex-wrap tw-items-end tw-gap-4">
      <Field label="Desde"><Calendar appendTo={document.body} className="tw-h-9" value={asDate(filters.from)} onChange={event => changeFilter('from', dateString(event.value))} dateFormat="dd/mm/yy" showIcon /></Field>
      <Field label="Hasta"><Calendar appendTo={document.body} className="tw-h-9" value={asDate(filters.to)} onChange={event => changeFilter('to', dateString(event.value))} dateFormat="dd/mm/yy" showIcon /></Field>
      <Field label="Vigencia"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.view} options={model.viewOptions} onChange={event => changeFilter('view', event.value)} /></Field>
      <Field label="Departamento"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.department} options={model.departmentOptions} onChange={event => changeFilter('department', event.value)} filter /></Field>
      <Field label="Prestación"><Dropdown appendTo={document.body} className="tw-h-9" value={filters.service} options={model.serviceOptions} onChange={event => changeFilter('service', event.value)} /></Field>
      <Field label="Búsqueda"><InputText className="tw-h-9" value={filters.search} onChange={event => changeFilter('search', event.target.value)} onKeyDown={event => event.key === 'Enter' && applyFilters()} placeholder="Texto, zona, agente o fecha" /></Field>
      <Button className="tw-h-9" label="Aplicar filtros" size="small" outlined onClick={applyFilters} /><Button className="tw-h-9" label="Limpiar" size="small" text onClick={clearFilters} />
    </div></Card>
    <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-2"><strong>{page.total} zonas</strong><div className="tw-flex tw-flex-wrap tw-gap-2">{model.canExport && <Button className="tw-h-9" label="Descargar reporte" icon="pi pi-download" size="small" outlined onClick={model.onExport} />}{model.canCreate && <Button className="tw-h-9" label="Registrar demora" icon="pi pi-plus" size="small" onClick={() => open('create')} />}</div></div>
    <Card className="tw-min-w-0 tw-max-w-full tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-0' }, content: { className: 'tw-p-0' } }}><DataTable stripedRows value={page.items} dataKey="id" size="small" className="phase-two-table delay-prime-table [&_.p-paginator-rpp-options_.p-dropdown-label]:tw-flex [&_.p-paginator-rpp-options_.p-dropdown-label]:tw-h-full [&_.p-paginator-rpp-options_.p-dropdown-label]:tw-items-center [&_.p-paginator-rpp-options_.p-dropdown-label]:tw-justify-center [&_.p-paginator-rpp-options_.p-dropdown-label]:tw-p-0" tableClassName="delay-data-table" rowClassName={row => row.needs_review ? 'delay-review-row' : row.is_current ? 'active-delay' : ''} emptyMessage="No hay demoras para los filtros seleccionados" aria-label="Zonas con demora" scrollable lazy paginator rows={50} rowsPerPageOptions={[50]} first={page.offset} totalRecords={page.total} onPage={event => loadPage(event.first)} sortField={sortField} sortOrder={sortOrder} onSort={changeSort}>
      <Column field="created_at" sortable header="Registrada" body={row => <span className="tw-whitespace-nowrap">{formatDate(row.created_at)}</span>} /><Column field="next_review_at" sortable header="Estado / revisión" body={row => row.status === 'NORMALIZADO' ? <Tag value="Histórica / normalizada" severity="secondary" /> : row.needs_review ? <div className="tw-grid tw-gap-1"><Tag value="Requiere revisión" severity="danger" /><small className="tw-whitespace-nowrap">desde {formatDate(row.next_review_at)}</small></div> : <div className="tw-grid tw-gap-1"><Tag value="Vigente" severity="success" /><small className="tw-whitespace-nowrap">revisar {formatDate(row.next_review_at)}</small></div>} />
      <Column field="service" sortable header="Prestación" body={row => displayService(row.service)} /><Column field="department" sortable header="Departamento" body={row => displayLocation(row.department)} /><Column field="zone" sortable header="Zona afectada" body={row => displayLocation(row.zone)} /><Column header="Tiempo / indicación" body={row => delayIndication(row)} /><Column field="agent" sortable header="Registró" /><Column header="Cierre" body={row => row.status === 'NORMALIZADO' ? <>{row.resolution_note || '—'}<small className="delay-close-meta">{row.normalized_by || '—'} · <span className="tw-whitespace-nowrap">{formatDate(row.normalized_at)}</span></small></> : '—'} /><Column header="Opciones" body={row => <div className="tw-flex tw-items-center tw-gap-1">{row.status === 'VIGENTE' && model.canNormalize && <Button type="button" label="Normalizar" icon="pi pi-check" size="small" text className="tw-h-9" disabled={busy} onClick={() => normalize(row)} />}<RowMenu id={`delay-${row.id}`} label={`Opciones de la demora en ${displayLocation(row.zone)}`} items={actionItems(row)} /></div>} frozen alignFrozen="right" />
    </DataTable></Card>
    <Dialog header={title} visible={Boolean(dialog)} onHide={close} modal appendTo={document.body} maskClassName="tw-z-[1100]" className="tw-overflow-visible" contentClassName="tw-overflow-y-auto" style={{ width: 'min(640px, 95vw)', maxHeight: '90vh' }} breakpoints={{ '640px': '95vw' }}><form onSubmit={save} className="tw-flex tw-flex-col tw-gap-3">
      {conflict && <div role="alert" className="tw-rounded-md tw-border tw-border-amber-400 tw-bg-amber-50 tw-p-3"><strong>Esta demora cambió mientras la editabas.</strong><p className="tw-mb-0">Tu nota permanece en el formulario. Revisá la tabla actualizada y abrí nuevamente la demora antes de guardar.</p></div>}
      {dialog?.row && dialog.kind !== 'create' && <div className="tw-grid tw-gap-1"><strong>{displayLocation(dialog.row.department)} · {displayLocation(dialog.row.zone)}</strong><span>{displayService(dialog.row.service)}</span><small>{dialog.row.message}</small></div>}
      {dialog?.kind === 'create' && <DelayCreateFields form={form} setForm={setForm} update={update} model={model} />}
      {dialog?.kind === 'verify' && <><Field label="¿Cómo se verificó que continúa vigente?"><InputTextarea value={form.verification_note || ''} onChange={event => update('verification_note', event.target.value)} rows={4} required /></Field><Field label="Volver a revisar en"><Dropdown appendTo={document.body} panelClassName="tw-z-[1200]" className="tw-h-9" value={form.review_minutes} options={reviewOptions} onChange={event => update('review_minutes', event.value)} /></Field></>}
      {dialog?.kind === 'history' && <div className="notice-timeline">{events.length ? events.map((entry, index) => <article key={entry.id || index}><strong>{statusNames[entry.event_type] || entry.event_type}</strong><time>{formatDate(entry.created_at)}</time><span>{entry.actor}</span>{entry.note && <p>{entry.note}</p>}{entry.review_due_at && <small>Próxima revisión: {formatDate(entry.review_due_at)}</small>}</article>) : <p>No hay eventos registrados.</p>}</div>}
      <div className="tw-flex tw-justify-end tw-gap-2"><Button className="tw-h-9" type="button" label={dialog?.kind === 'history' ? 'Cerrar' : 'Cancelar'} text onClick={close} disabled={busy} />{dialog?.kind !== 'history' && <Button className="tw-h-9" type="submit" label={busy ? 'Guardando…' : dialog?.kind === 'verify' ? 'Renovar vigencia' : 'Guardar'} loading={busy} disabled={busy || conflict} />}</div>
    </form></Dialog>
  </div>;
}

export function NoticesView({ model }) {
  const [filters, setFilters] = useState(model.filters);
  const [appliedFilters, setAppliedFilters] = useState(model.filters);
  const [view, setView] = useState(model.activeView);
  const [page, setPage] = useState(model.page);
  const [sortOrder, setSortOrder] = useState(-1);
  const requestSequence = useRef(0);
  useEffect(() => () => { requestSequence.current += 1; }, []);
  const statusDropdownRefs = useRef(new Map());
  const [dialog, setDialog] = useState(null);
  const dialogTrigger = useRef(null);
  const [form, setForm] = useState(noticeBlank);
  const [events, setEvents] = useState([]);
  const [assignees, setAssignees] = useState([]);
  const [duplicate, setDuplicate] = useState(null);
  const [conflictCurrent, setConflictCurrent] = useState(null);
  const [conflictPending, setConflictPending] = useState(false);
  const conflictSequence = useRef(0);
  const load = async (nextFilters = appliedFilters, nextView = view, nextOffset = 0, nextLimit = page.limit || 50, nextSortOrder = sortOrder) => {
    const sequence = ++requestSequence.current;
    const query = new URLSearchParams();
    for (const [name, value] of Object.entries({ date_from: nextFilters.from, date_to: nextFilters.to, status: nextFilters.status, task: nextFilters.task, contact: nextFilters.contact, q: nextFilters.search, scope: nextView, offset: nextOffset, limit: nextLimit, sort_order: nextSortOrder === 1 ? 'asc' : 'desc' })) if (value !== '' && value != null) query.set(name, value);
    const response = await model.request(`/api/notices/page?${query}`);
    if (sequence !== requestSequence.current) return response;
    if (response.offset > 0 && response.offset >= response.total) return load(nextFilters, nextView, Math.max(0, Math.floor((response.total - 1) / nextLimit) * nextLimit), nextLimit, nextSortOrder);
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
  const close = () => { conflictSequence.current += 1; setDialog(null); setForm(noticeBlank); setEvents([]); setDuplicate(null); setConflictCurrent(null); setConflictPending(false); window.requestAnimationFrame(() => { if (dialogTrigger.current?.isConnected) dialogTrigger.current.focus(); }); };
  const open = (kind, row = null, status = 'RESUELTO') => { dialogTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; conflictSequence.current += 1; setConflictCurrent(null); setConflictPending(false); setForm({ ...noticeBlank, comments: row?.comments || '', managed_by: row?.managed_by || '', status }); setDialog({ kind, row }); };
  const loadConflict = row => {
    const sequence = ++conflictSequence.current;
    setConflictPending(true);
    return model.request(`/api/notices/${row.id}`).then(item => { if (sequence === conflictSequence.current) setConflictCurrent(item); }).catch(error => { if (sequence === conflictSequence.current && !error.stale) notify('error', 'No se pudo consultar la versión actual', errorText(error)); });
  };
  const continueDraft = () => {
    if (!conflictCurrent || dialog?.row?.id !== conflictCurrent.id) return;
    setDialog(current => ({ ...current, row: conflictCurrent }));
    setConflictCurrent(null);
    setConflictPending(false);
  };
  const assign = async row => { try { setAssignees(await model.request('/api/notices/assignees')); open('assign', row); } catch (error) { notify('error', 'No se pudieron cargar responsables', errorText(error)); } };
  const history = async row => { try { setEvents(await model.request(`/api/notices/${row.id}/history`)); open('history', row); } catch (error) { notify('error', 'No se pudo cargar el historial', errorText(error)); } };
  const save = async event => {
    event.preventDefault();
    if (conflictPending) return;
    const { kind, row } = dialog;
    if (kind === 'create') {
      if (!form.notice_type || form.detail.trim().length < 2) { notify('error', 'Faltan datos', 'Seleccioná un motivo y escribí el detalle.'); return; }
      const body = { task_number: form.task_number.trim() || null, phone: form.phone.trim() || null, notice_type: form.notice_type, audience: form.audience, detail: form.detail.trim(), communicated_by: model.currentUser, status: 'PENDIENTE', managed_by: form.managed_by ? model.currentUser : null };
      if (!duplicate) {
        try { const matches = await model.request(`/api/notices/duplicates?${new URLSearchParams({ task_number: body.task_number || '', phone: body.phone || '', notice_type: body.notice_type })}`); if (matches.length) { setDuplicate(matches[0]); return; } }
        catch (error) { notify('error', 'No se pudo verificar el aviso', errorText(error)); return; }
      }
      run(() => model.request('/api/notices', { method: 'POST', body: JSON.stringify({ ...body, allow_duplicate: Boolean(duplicate) }) }), 'Aviso registrado', close, error => {
        if (error.payload?.detail?.duplicate) setDuplicate(error.payload.detail.duplicate);
      });
    } else if (kind === 'comment') run(() => model.request(`/api/notices/${row.id}/status`, { method: 'PATCH', body: JSON.stringify({ expected_revision: row.revision, comments: form.comments || null }) }), 'Comentario guardado', close,()=>loadConflict(row));
    else if (kind === 'assign') run(() => model.request(`/api/notices/${row.id}/status`, { method: 'PATCH', body: JSON.stringify({ expected_revision: row.revision, managed_by: typeof form.managed_by === 'string' && form.managed_by !== 'Sin responsable' ? form.managed_by.trim() || null : null }) }), 'Responsable actualizado', close,()=>loadConflict(row));
    else if (kind === 'close') {
      if ((form.comments || '').trim().length < 2) { notify('error', 'Faltan datos', 'Indicá el resultado o motivo del cierre.'); return; }
      run(() => model.request(`/api/notices/${row.id}/status`, { method: 'PATCH', body: JSON.stringify({ expected_revision: row.revision, status: form.status, comments: form.comments.trim() }) }), form.status === 'RESUELTO' ? 'Aviso resuelto' : 'Aviso cancelado', close,()=>loadConflict(row));
    }
  };
  const changeStatus = (row, status) => {
    if (['RESUELTO', 'CANCELADO'].includes(status)) return open('close', row, status);
    run(() => model.request(`/api/notices/${row.id}/status`, { method: 'PATCH', body: JSON.stringify({ expected_revision: row.revision, status, ...(!row.managed_by && model.canAssign ? { managed_by: model.currentUser } : {}) }) }), `Estado: ${statusNames[status]}`);
  };
  const actions = row => [
    { label: 'Ver aviso completo', icon: 'pi pi-eye', command: () => open('detail', row) },
    ...(model.canAssign ? [{ label: row.managed_by ? 'Reasignar' : 'Asignar', icon: 'pi pi-user-plus', command: () => assign(row) }] : []),
    ...(model.canComment ? [{ label: 'Editar seguimiento', icon: 'pi pi-pencil', command: () => open('comment', row) }] : []),
    { label: 'Historial', icon: 'pi pi-history', command: () => history(row) }
  ];
  const closeOtherStatusDropdowns = id => {
    for (const [otherId, dropdown] of statusDropdownRefs.current) if (otherId !== id) dropdown.hide();
  };
  const closeNoticeMenu = event => {
    if (activeRowMenu?.id?.startsWith('notice-')) activeRowMenu.menu.current?.hide({ currentTarget: event?.currentTarget || document.body });
  };
  const statusOptions = [
    ...(model.canChangeStatus ? ['PENDIENTE', 'EN_GESTION', 'ESPERANDO_RESPUESTA'] : []),
    ...(model.canClose ? ['RESUELTO', 'CANCELADO'] : [])
  ].map(status => ({ label: statusNames[status], value: status }));
  const draftAtConflict = dialog?.row && {
    status: dialog.kind === 'close' ? form.status : dialog.row.status,
    managed_by: dialog.kind === 'assign' ? form.managed_by : dialog.row.managed_by,
    comments: ['comment', 'close'].includes(dialog.kind) ? form.comments : dialog.row.comments
  };
  const title = { create: 'Registrar nuevo aviso', comment: 'Editar seguimiento', assign: 'Asignar aviso', close: 'Cerrar aviso', history: 'Historial del aviso', detail: 'Aviso completo' }[dialog?.kind];
  const changeFilter = (key, value) => setFilters(current => ({ ...current, [key]: value }));
  return <div className="operational-view notice-prime-view tw-flex tw-min-w-0 tw-flex-col tw-gap-3 tw-text-[13px]">
    <Toast ref={toast} />
    <section className="tw-grid tw-grid-cols-1 tw-gap-3 sm:tw-grid-cols-2 xl:tw-grid-cols-4" aria-label="Indicadores de avisos">{model.metrics.map(metric => <Card key={metric.value} className={`notice-prime-metric tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm ${metric.tone} ${view === metric.value ? 'notice-prime-metric-active' : ''}`} pt={{ body: { className: 'tw-p-0' }, content: { className: 'tw-p-0' } }}><button type="button" className={`tw-grid tw-w-full tw-gap-1 tw-rounded-md tw-border-0 tw-border-l-4 tw-border-solid tw-p-3 tw-text-left tw-text-[var(--text)] [&>span]:tw-text-xs [&>span]:tw-text-[var(--text-muted)] [&>strong]:tw-text-2xl [&>small]:tw-text-xs [&>small]:tw-text-[var(--text-muted)] ${view === metric.value ? 'tw-bg-[var(--color-primary-bg)]' : 'tw-bg-transparent'} ${metric.tone === 'urgent' ? 'tw-border-[var(--color-urgente)]' : metric.tone === 'mine' ? 'tw-border-[var(--color-ok)]' : metric.tone === 'waiting' ? 'tw-border-[var(--color-espera)]' : 'tw-border-slate-400'}`} onClick={() => selectView(metric.value)} aria-pressed={view === metric.value}><span>{metric.label}</span><strong>{metricCounts[metric.value]}</strong><small>{metric.help}</small></button></Card>)}</section>
    <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-2"><strong>{page.total} avisos</strong><div className="tw-flex tw-flex-wrap tw-gap-2">{model.canExport && <Button className="tw-h-9" label="Descargar esta vista" icon="pi pi-download" size="small" outlined onClick={model.onExport} />}{model.canCreate && <Button className="tw-h-9" label="Nuevo aviso" icon="pi pi-plus" size="small" onClick={() => open('create')} />}</div></div>
    <Card className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-3' } }}><div className="tw-flex tw-flex-wrap tw-items-end tw-gap-3"><Field label="Vista" className="tw-w-[200px] tw-shrink-0"><Dropdown appendTo={document.body} scrollHeight="264px" pt={noticeViewDropdownPt} panelClassName="tw-p-1" className="tw-h-9 tw-w-full" value={view} options={model.viewOptions} valueTemplate={option => <span className="tw-flex tw-h-full tw-min-w-0 tw-items-center tw-text-[13px]">{option?.label || 'Seleccionar vista'}</span>} onChange={event => selectView(event.value)} /></Field><Field label="Desde" className="tw-w-[160px] tw-shrink-0"><Calendar appendTo={document.body} locale="es" panelClassName={noticeCalendarPanel} className="tw-h-9 tw-w-full tw-min-w-0" inputClassName="tw-w-full tw-min-w-0" value={asDate(filters.from)} onChange={event => changeFilter('from', dateString(event.value))} dateFormat="dd/mm/yy" showIcon /></Field><Field label="Hasta" className="tw-w-[160px] tw-shrink-0"><Calendar appendTo={document.body} locale="es" panelClassName={noticeCalendarPanel} className="tw-h-9 tw-w-full tw-min-w-0" inputClassName="tw-w-full tw-min-w-0" value={asDate(filters.to)} onChange={event => changeFilter('to', dateString(event.value))} dateFormat="dd/mm/yy" showIcon /></Field><Field label="Estado" className="tw-w-[200px] tw-shrink-0"><Dropdown appendTo={document.body} scrollHeight="264px" pt={noticeDropdownPt} className="tw-h-9 tw-w-full" value={filters.status} options={model.statusOptions} onChange={event => changeFilter('status', event.value)} /></Field><Field label="Tarea" className="tw-w-[140px] tw-shrink-0"><InputText className="tw-h-9 tw-w-full" value={filters.task} onChange={event => changeFilter('task', event.target.value)} onKeyDown={event => event.key === 'Enter' && apply(filters)} /></Field><Field label="Teléfono" className="tw-w-[180px] tw-shrink-0"><InputText className="tw-h-9 tw-w-full" value={filters.contact} onChange={event => changeFilter('contact', event.target.value)} onKeyDown={event => event.key === 'Enter' && apply(filters)} /></Field><Field label="Búsqueda" className="tw-w-[250px] tw-shrink-0"><InputText className="tw-h-9 tw-w-full" value={filters.search} onChange={event => changeFilter('search', event.target.value)} onKeyDown={event => event.key === 'Enter' && apply(filters)} /></Field><div className="tw-flex tw-shrink-0 tw-items-end tw-gap-2"><Button className="tw-h-9 tw-whitespace-nowrap" label="Aplicar filtros" size="small" outlined onClick={() => apply(filters)} /><Button className="tw-h-9 tw-whitespace-nowrap" label="Limpiar" size="small" text onClick={clear} /></div></div></Card>
    <Card className="notice-prime-table-card tw-min-w-0 tw-max-w-full tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body: { className: 'tw-p-0' }, content: { className: 'tw-p-0' } }}><DataTable stripedRows value={rows} dataKey="id" size="small" pt={{ paginator: { RPPDropdown: { input: { style: { display: 'flex', justifyContent: 'center', alignItems: 'center', paddingLeft: 0, paddingRight: 0 } } } } }} className={`notice-prime-table tw-min-w-0 [&_.p-datatable-wrapper]:tw-overflow-x-hidden max-sm:[&_.p-datatable-thead]:tw-hidden max-sm:[&_.p-datatable-tbody>tr]:tw-grid max-sm:[&_.p-datatable-tbody>tr]:tw-grid-cols-2 max-sm:[&_.p-datatable-tbody>tr>td]:tw-w-full max-sm:[&_.p-datatable-tbody>tr>td:nth-child(3)]:tw-col-span-2 ${showComments ? 'max-sm:[&_.p-datatable-tbody>tr>td:nth-child(6)]:tw-col-span-2 max-sm:[&_.p-datatable-tbody>tr>td:nth-child(7)]:tw-col-span-2' : 'max-sm:[&_.p-datatable-tbody>tr>td:nth-child(6)]:tw-col-span-2'}`} tableClassName="notice-table tw-table-fixed tw-w-full" emptyMessage="No hay avisos para esos filtros" aria-label="Avisos del equipo" lazy paginator sortField="created_at" sortOrder={sortOrder} onSort={event => { const nextOrder = event.sortOrder || -1; setSortOrder(nextOrder); load(appliedFilters, view, 0, page.limit || 50, nextOrder).catch(error => notify('error', 'No se pudo ordenar la tabla', errorText(error))); }} rows={page.limit || 50} first={page.offset} totalRecords={page.total} onPage={event => { const offset = event.rows === page.limit ? event.first : 0; model.onStateChange?.(appliedFilters, view, event.rows); load(appliedFilters, view, offset, event.rows).catch(error => notify('error', 'No se pudo cambiar de página', errorText(error))); }} onRowClick={event => open('detail', event.data)} rowClassName={() => 'tw-cursor-pointer'}>
      <Column field="created_at" header="Tiempo" sortable style={{ width: showComments ? '11%' : '13%' }} body={row => <div className="tw-flex tw-min-w-0 tw-flex-col tw-gap-1"><span className="tw-whitespace-nowrap">{formatNoticeTime(row.created_at)}</span><span className="tw-text-xs tw-text-slate-500">Hace {model.age(row).replace(/\s+/g, '')}</span></div>} />
      <Column header="Tarea" style={{ width: showComments ? '13%' : '15%' }} body={row => <div className="tw-flex tw-min-w-0 tw-flex-col tw-gap-1 tw-break-words">{row.task_number ? <a className="tw-font-semibold tw-text-blue-600 tw-break-words" href={`https://aps.portoservicios.uy/3/tareas/${encodeURIComponent(row.task_number)}`} target="_blank" rel="noopener noreferrer" onClick={event => event.stopPropagation()}>{row.task_number}</a> : <span>Sin tarea</span>}<span className="tw-text-xs tw-break-words">{row.phone || 'Sin teléfono'}</span></div>} />
      <Column header="Motivo y resumen" style={{ width: showComments ? '20%' : '26%' }} body={row => <div className="tw-flex tw-w-full tw-min-w-0 tw-flex-col tw-gap-1"><strong className="tw-whitespace-normal tw-break-words tw-font-semibold">{row.notice_type}</strong><span className="tw-block tw-w-full tw-min-w-0 tw-truncate tw-text-slate-500" title={row.detail}>{row.detail}</span></div>} />
      <Column header="Responsable" style={{ width: showComments ? '14%' : '18%' }} body={row => <div className="tw-flex tw-flex-col tw-items-start tw-justify-center tw-gap-1 tw-w-full tw-min-w-0 tw-whitespace-normal tw-break-words">{row.managed_by ? <span className="tw-font-medium tw-whitespace-normal tw-break-words">{row.managed_by}</span> : model.canAssign && !noticeIsClosed(row) ? <Button className="tw-h-9 tw-whitespace-nowrap tw-max-w-full" label="Asignarme" size="small" onClick={event => { event.stopPropagation(); run(() => model.request(`/api/notices/${row.id}/status`, { method: 'PATCH', body: JSON.stringify({ expected_revision: row.revision, managed_by: model.currentUser }) }), 'Aviso asignado'); }} /> : <span className="tw-text-slate-500">Sin responsable</span>}</div>} />
      <Column header="Estado" style={{ width: showComments ? '21%' : '22%' }} body={row => <div onClick={event => event.stopPropagation()}>{statusOptions.length ? <NoticeStatusDropdown row={row} statusOptions={statusOptions} dropdownRefs={statusDropdownRefs} closeOtherStatusDropdowns={closeOtherStatusDropdowns} closeNoticeMenu={closeNoticeMenu} changeStatus={changeStatus} /> : <Tag value={noticeState(row).label} severity={noticeState(row).severity} className="tw-whitespace-nowrap tw-text-center tw-text-[13px] tw-px-2 tw-py-1" />}</div>} />
      {showComments && <Column header="Comentarios" style={{ width: '16%' }} body={row => <span className="tw-whitespace-normal tw-break-words">{row.comments || 'Sin comentario de cierre'}</span>} />}
      <Column header={<span title="Acciones" aria-label="Acciones">⋮</span>} style={{ width: '6%' }} body={row => <RowMenu id={`notice-${row.id}`} label={`Acciones del aviso ${row.task_number || row.id}`} items={actions(row)} onBeforeToggle={() => closeOtherStatusDropdowns()} />} />
    </DataTable></Card>
    <Dialog header={title} visible={Boolean(dialog)} onHide={close} modal appendTo={document.body} style={{ width: 'min(640px, 95vw)' }}><form onSubmit={save} className="tw-flex tw-flex-col tw-gap-4">
      {conflictPending && <div role="alert" className="tw-rounded-md tw-border tw-border-amber-400 tw-bg-amber-50 tw-p-3 tw-text-[13px]"><strong>El aviso cambió mientras lo editabas.</strong><p className="tw-my-2">Tu borrador sigue en el formulario. Compará los datos antes de continuar.</p>{conflictCurrent ? <><div className="tw-grid tw-grid-cols-[auto_1fr_1fr] tw-gap-2 tw-break-words"><strong>Campo</strong><strong>Tu borrador</strong><strong>Versión vigente</strong>{[['Estado', statusNames[draftAtConflict.status] || draftAtConflict.status, statusNames[conflictCurrent.status] || conflictCurrent.status], ['Responsable', draftAtConflict.managed_by || 'Sin responsable', conflictCurrent.managed_by || 'Sin responsable'], ['Comentarios', draftAtConflict.comments || 'Sin comentario', conflictCurrent.comments || 'Sin comentario']].map(([label, draft, current]) => <React.Fragment key={label}><span>{label}</span><span>{draft}</span><span>{current}</span></React.Fragment>)}</div><div className="tw-mt-3 tw-flex tw-flex-wrap tw-gap-2"><Button type="button" size="small" label="Conservar borrador y continuar" onClick={continueDraft} /><Button type="button" size="small" label="Descartar borrador" text onClick={close} /></div><small className="tw-mt-2 tw-block">Continuar solo actualiza la revisión del formulario; tendrás que pulsar Guardar nuevamente.</small></> : <Button type="button" text size="small" label="Consultar versión vigente" onClick={() => loadConflict(dialog.row)} />}</div>}
      {dialog?.kind === 'create' && <div className="tw-grid tw-grid-cols-1 tw-gap-3 md:tw-grid-cols-2"><Field label="Número de tarea"><InputText className="tw-h-9" value={form.task_number} onChange={event => update('task_number', event.target.value)} maxLength={120} /></Field><Field label="Teléfono del cliente"><InputText className="tw-h-9" value={form.phone} onChange={event => update('phone', event.target.value)} maxLength={80} /></Field><Field label="Motivo"><Dropdown appendTo={document.body} scrollHeight="264px" pt={noticeDropdownPt} className="tw-h-9" value={form.notice_type} options={options(noticeTypes)} filter onChange={event => { update('notice_type', event.value); setDuplicate(null); }} placeholder="Seleccionar motivo" /></Field><Field label="Dirigido a"><Dropdown appendTo={document.body} scrollHeight="264px" pt={noticeDropdownPt} className="tw-h-9" value={form.audience} options={[{ label: 'Todo el equipo', value: 'TODOS' }, { label: 'Telefonistas', value: 'TELEFONISTAS' }, { label: 'Planificadores', value: 'PLANIFICADORES' }]} onChange={event => update('audience', event.value)} /></Field><Field label="¿Qué necesita saber o hacer el equipo?" wide><InputTextarea value={form.detail} onChange={event => update('detail', event.target.value)} rows={6} maxLength={4000} required /></Field>{model.canAssign && <label className="tw-flex tw-items-center tw-gap-2"><input type="checkbox" checked={Boolean(form.managed_by)} onChange={event => update('managed_by', event.target.checked)} />Asignármelo al guardar</label>}</div>}
      {duplicate && dialog?.kind === 'create' && <div className="tw-rounded-md tw-border tw-border-amber-300 tw-bg-amber-50 tw-p-3"><strong>Posible aviso duplicado</strong><p>{duplicate.duplicate_reason}</p><p>Tarea: {duplicate.task_number || 'Sin tarea'} · Estado: {statusNames[duplicate.status] || duplicate.status}</p><Button className="tw-h-9" type="button" label="Ver aviso existente" text onClick={() => { close(); findExisting(duplicate); }} /><small>Si es otro caso, guardalo como caso independiente.</small></div>}
      {dialog?.kind === 'comment' && <Field label="Comentario de seguimiento"><InputTextarea value={form.comments || ''} onChange={event => update('comments', event.target.value)} rows={7} /></Field>}
      {dialog?.kind === 'assign' && <Field label="Responsable"><Dropdown appendTo={document.body} scrollHeight="264px" pt={noticeDropdownPt} className="tw-h-9" value={form.managed_by} optionValue="value" options={[{ label: 'Sin responsable', value: '' }, ...assignees.map(person => ({ label: `${person.display_name} · ${person.role_name}`, value: person.display_name }))]} onChange={event => update('managed_by', event.value)} filter /></Field>}
      {dialog?.kind === 'close' && <><Field label="Resultado"><Dropdown appendTo={document.body} scrollHeight="264px" pt={noticeDropdownPt} className="tw-h-9" value={form.status} options={[{ label: 'Resuelto', value: 'RESUELTO' }, { label: 'Cancelado', value: 'CANCELADO' }]} onChange={event => update('status', event.value)} /></Field><Field label="Resultado o motivo del cierre"><InputTextarea value={form.comments || ''} onChange={event => update('comments', event.target.value)} rows={6} maxLength={4000} required /></Field></>}
      {dialog?.kind === 'history' && <div className="notice-timeline">{events.length ? events.map((entry, index) => <article key={entry.id || index}><strong>{entry.event_type}</strong><time>{formatDate(entry.created_at)}</time><span>{entry.actor}</span>{entry.comment && <p>{entry.comment}</p>}{entry.detail && <small>{entry.detail}</small>}</article>) : <p>No hay movimientos registrados.</p>}</div>}
      {dialog?.kind === 'detail' && <div className="tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]">
        <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-3"><Tag value={noticeState(dialog.row).label} severity={noticeState(dialog.row).severity} /><strong className="tw-font-bold tw-text-[var(--text)]">{dialog.row.notice_type}</strong></div>
        <div className="tw-grid tw-grid-cols-1 tw-gap-3 sm:tw-grid-cols-2">
          {[['Registrado', formatDate(dialog.row.created_at)], ['Tarea', dialog.row.task_number || 'Sin tarea'], ['Teléfono', dialog.row.phone || 'Sin teléfono'], ['Responsable', dialog.row.managed_by || 'Sin responsable'], ['Destinatario', dialog.row.audience || '—'], ['Dio aviso', dialog.row.communicated_by || '—']].map(([label, value]) => <div key={label} className="tw-flex tw-min-w-0 tw-flex-col tw-overflow-hidden tw-rounded-md tw-border tw-border-[var(--border)]">
            <span className="tw-border-b tw-border-[var(--border)] tw-bg-[var(--surface-subtle)] tw-px-3 tw-py-2 tw-font-bold tw-text-[var(--text)]">{label}</span>
            {label === 'Tarea' && dialog.row.task_number ? <a className="tw-bg-[var(--surface)] tw-px-3 tw-py-2 tw-font-normal tw-text-blue-600 tw-whitespace-normal tw-break-words hover:tw-underline" href={`https://aps.portoservicios.uy/3/tareas/${encodeURIComponent(dialog.row.task_number)}`} target="_blank" rel="noopener noreferrer">{value}</a> : <span className="tw-bg-[var(--surface)] tw-px-3 tw-py-2 tw-font-normal tw-whitespace-normal tw-break-words">{value}</span>}
          </div>)}
        </div>
        {[['Detalle completo', dialog.row.detail || '—'], ['Comentarios', dialog.row.comments || 'Sin comentarios']].map(([label, value]) => <div key={label} className="tw-min-w-0 tw-overflow-hidden tw-rounded-md tw-border tw-border-[var(--border)]">
          <div className="tw-border-b tw-border-[var(--border)] tw-bg-[var(--surface-subtle)] tw-px-3 tw-py-2 tw-font-bold tw-text-[var(--text)]">{label}</div>
          <p className="tw-m-0 tw-bg-[var(--surface)] tw-p-3 tw-font-normal tw-whitespace-pre-wrap tw-break-words">{value}</p>
        </div>)}
      </div>}
      <div className="tw-flex tw-justify-end tw-gap-2"><Button className="tw-h-9" type="button" label={['history', 'detail'].includes(dialog?.kind) ? 'Cerrar' : 'Cancelar'} text onClick={close} disabled={busy} />{!['history', 'detail'].includes(dialog?.kind) && <Button className="tw-h-9" type="submit" label={busy ? 'Guardando…' : 'Guardar'} loading={busy} disabled={busy || conflictPending} />}</div>
    </form></Dialog>
  </div>;
}
