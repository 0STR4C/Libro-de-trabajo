import React, { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { InputSwitch } from 'primereact/inputswitch';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { createArrivalPageRequests } from './arrival-times-requests.js';

const ALL_DEPARTMENT = 'Todo el departamento';
const emptyForm = { service: '', department: '', zone: ALL_DEPARTMENT, base_estimated_minutes: null, is_active: true };
const asOptions = values => values.map(value => ({ label: value, value }));
const field = (label, control) => <label className="tw-flex tw-min-w-0 tw-flex-col tw-gap-1 tw-text-[13px] tw-font-medium"><span>{label}</span>{control}</label>;

export function ArrivalTimesView({ model, active = true }) {
  const [filters, setFilters] = useState(model.filters);
  const [page, setPage] = useState(model.page);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editingRevision, setEditingRevision] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [conflictCurrent, setConflictCurrent] = useState(null);
  const [deactivateCandidate, setDeactivateCandidate] = useState(null);
  const toast = useRef(null);
  const pageRequests = useRef(null);
  if (!pageRequests.current) pageRequests.current = createArrivalPageRequests();
  const activeRef = useRef(active);
  const pageRef = useRef(page);
  const modelRef = useRef(model);
  const interaction = useRef(0);
  const filterTransition = useRef(false);
  const reloadWhenActive = useRef(false);
  const dialogSequence = useRef(0);
  const currentReadSequence = useRef(0);
  const visibleRef = useRef(false);
  const writeInFlight = useRef(false);
  activeRef.current = active;
  pageRef.current = page;
  modelRef.current = model;
  visibleRef.current = visible;
  useEffect(() => () => { pageRequests.current.invalidate(); dialogSequence.current += 1; currentReadSequence.current += 1; }, []);
  useEffect(() => {
    if (!active) { pageRequests.current.invalidate(); currentReadSequence.current += 1; setLoading(false); }
  }, [active]);

  useEffect(() => {
    pageRequests.current.invalidate();
    if (!active) return;
    filterTransition.current = false;
    setLoading(false);
    setFilters(model.filters);
    pageRef.current = model.page;
    setPage(model.page);
    if (reloadWhenActive.current) { reloadWhenActive.current = false; void loadPage(model.page?.offset || 0); }
  }, [model.filters, model.page, active]);
  const notify = (severity, detail) => toast.current?.show({ severity, summary: severity === 'error' ? 'Error' : 'Listo', detail, life: 4000 });
  const change = (name, value) => setForm(previous => ({ ...previous, [name]: value }));
  const departments = model.geography?.departments || {};
  const services = model.geography?.services || [];
  const zones = form.department ? departments[form.department] || [ALL_DEPARTMENT] : [];

  const loadPage = (offset) => {
    if (!activeRef.current || filterTransition.current) return Promise.resolve(false);
    setLoading(true);
    return pageRequests.current.load(async () => {
      const currentModel = modelRef.current;
      let result = await currentModel.onPage(offset);
      if (offset > 0 && offset >= result.total) {
        const last = Math.max(0, Math.floor((result.total - 1) / 50) * 50);
        result = await currentModel.onPage(last);
      }
      return result;
    }, {
      isActive: () => activeRef.current && !filterTransition.current,
      accept: result => { pageRef.current = result; setPage(result); },
      reject: error => notify('error', error.message),
      finish: () => setLoading(false),
    });
  };

  const refreshAfterWrite = async () => {
    if (!activeRef.current) { reloadWhenActive.current = true; return; }
    const refreshed = await loadPage(pageRef.current?.offset || 0);
    if (!refreshed && !activeRef.current) reloadWhenActive.current = true;
  };

  const loadCurrentVersion = async (id, sourceForm, ticket) => {
    const read = ++currentReadSequence.current;
    const url = id ? `/api/arrival-times/${id}` : `/api/arrival-times/match?${new URLSearchParams({
      service: sourceForm.service, department: sourceForm.department, zone: sourceForm.zone,
    })}`;
    try {
      const current = await modelRef.current.request(url);
      if (ticket === dialogSequence.current && read === currentReadSequence.current && visibleRef.current && activeRef.current) setConflictCurrent(current);
    } catch (error) {
      if (ticket === dialogSequence.current && read === currentReadSequence.current && visibleRef.current && activeRef.current && !error.stale) notify('error', 'No se pudo consultar la versión vigente. Reintentá la comparación.');
    }
  };

  const close = (force = false) => {
    if (writeInFlight.current && force !== true) return;
    dialogSequence.current += 1;
    currentReadSequence.current += 1;
    visibleRef.current = false;
    setVisible(false);
  };

  const open = row => {
    dialogSequence.current += 1;
    currentReadSequence.current += 1;
    visibleRef.current = true;
    setConflict(false);
    setConflictCurrent(null);
    setEditingId(row?.id || null);
    setEditingRevision(row?.revision || null);
    setForm(row ? {
      service: row.service, department: row.department, zone: row.zone,
      base_estimated_minutes: row.base_estimated_minutes, is_active: row.is_active
    } : { ...emptyForm });
    setVisible(true);
  };

  const save = async event => {
    event.preventDefault();
    if (writeInFlight.current) return;
    if (conflict) { notify('error', 'Compará la versión vigente antes de volver a guardar.'); return; }
    if (!form.service || !form.department || !form.zone || !form.base_estimated_minutes) {
      notify('error', 'Completá servicio, departamento, zona y tiempo base');
      return;
    }
    const dialogTicket = dialogSequence.current;
    const interactionTicket = interaction.current;
    const sourceForm = { ...form };
    const itemId = editingId;
    writeInFlight.current = true;
    setSaving(true);
    try {
      await model.request(itemId ? `/api/arrival-times/${itemId}` : '/api/arrival-times', {
        method: itemId ? 'PATCH' : 'POST', body: JSON.stringify(itemId ? { ...sourceForm, expected_revision: editingRevision } : sourceForm)
      });
      pageRequests.current.invalidate();
      if (dialogTicket === dialogSequence.current) close(true);
      notify('success', itemId ? 'Tiempo de arribo actualizado' : 'Tiempo de arribo registrado');
      await refreshAfterWrite();
    } catch (error) {
      if (!error.stale) {
        notify('error', error.message);
        if (error.status === 409) {
          if (dialogTicket === dialogSequence.current) setConflict(true);
          if (interactionTicket === interaction.current && activeRef.current && !filterTransition.current) void loadPage(pageRef.current?.offset || 0);
          if (dialogTicket === dialogSequence.current && activeRef.current) void loadCurrentVersion(itemId, sourceForm, dialogTicket);
        } else if (error.uncertain) {
          if (interactionTicket === interaction.current && activeRef.current && !filterTransition.current) void loadPage(pageRef.current?.offset || 0);
        }
      }
    } finally { writeInFlight.current = false; setSaving(false); }
  };

  const deactivate = async row => {
    if (writeInFlight.current) return;
    writeInFlight.current = true;
    setDeactivateCandidate(null);
    const interactionTicket = interaction.current;
    try {
      await model.request(`/api/arrival-times/${row.id}?expected_revision=${row.revision}`, { method: 'DELETE' });
      pageRequests.current.invalidate();
      notify('success', 'Tiempo de arribo desactivado');
      await refreshAfterWrite();
    } catch (error) {
      if (!error.stale) {
        notify('error', error.message);
        if ((error.status === 409 || error.uncertain) && interactionTicket === interaction.current && activeRef.current) void loadPage(pageRef.current?.offset || 0);
      }
    } finally { writeInFlight.current = false; }
  };

  const pageChanged = event => { interaction.current += 1; return loadPage(event.first); };

  const applyFilters = async (operation) => {
    interaction.current += 1;
    pageRequests.current.invalidate();
    filterTransition.current = true;
    setLoading(false);
    try {
      const completed = await operation();
      if (!completed) filterTransition.current = false;
      return completed;
    } catch (error) {
      filterTransition.current = false;
      if (!error.stale) notify('error', error.message);
      return false;
    }
  };
  const apply = () => applyFilters(() => model.onApply(filters));
  const clear = () => { setFilters({ department: '', service: '', status: 'all' }); return applyFilters(model.onClear); };
  const adoptCurrent = () => {
    if (!conflictCurrent) return;
    const current = conflictCurrent;
    setEditingId(current.id);
    setEditingRevision(current.revision);
    setForm({ service: current.service, department: current.department, zone: current.zone,
      base_estimated_minutes: current.base_estimated_minutes, is_active: current.is_active });
    setConflict(false);
    setConflictCurrent(null);
  };
  const headerClass = 'tw-whitespace-normal tw-break-words';

  return <div className="tw-flex tw-min-w-0 tw-flex-col tw-gap-3 tw-text-[13px]">
    <Toast ref={toast} />
    <div className="tw-flex tw-w-full tw-flex-wrap tw-items-center tw-justify-between tw-gap-3">
      <h1 className="tw-m-0 tw-text-xl tw-font-semibold">Tiempos de arribo</h1>
      {model.canManage && <Button label="Nuevo tiempo" icon="pi pi-plus" size="small" className="tw-h-9" onClick={() => open(null)} />}
    </div>

    <section className="tw-rounded-md tw-border tw-border-[var(--border)] tw-bg-[var(--surface)] tw-p-4 tw-shadow-sm">
      <div className="tw-flex tw-w-full tw-flex-wrap tw-items-end tw-gap-3">
        {field('Departamento', <Dropdown appendTo={document.body} value={filters.department} options={[{ label: 'Todos los departamentos', value: '' }, ...asOptions(Object.keys(departments))]} onChange={event => setFilters(previous => ({ ...previous, department: event.value }))} className="tw-w-full tw-min-w-[190px]" />)}
        {field('Servicio', <Dropdown appendTo={document.body} value={filters.service} options={[{ label: 'Todos los servicios', value: '' }, ...asOptions(services)]} onChange={event => setFilters(previous => ({ ...previous, service: event.value }))} className="tw-w-full tw-min-w-[150px]" />)}
        {field('Estado', <Dropdown appendTo={document.body} value={filters.status} options={[{ label: 'Todos', value: 'all' }, { label: 'Activos', value: 'active' }, { label: 'Inactivos', value: 'inactive' }]} onChange={event => setFilters(previous => ({ ...previous, status: event.value }))} className="tw-w-full tw-min-w-[130px]" />)}
        <div className="tw-flex tw-w-full tw-flex-wrap tw-items-center tw-gap-3 sm:tw-w-auto">
          <Button label="Filtrar" icon="pi pi-filter" size="small" className="tw-h-9" onClick={apply} />
          <Button label="Limpiar" text size="small" className="tw-h-9" onClick={clear} />
        </div>
      </div>
    </section>

    <section className="tw-min-w-0 tw-rounded-md tw-border tw-border-[var(--border)] tw-bg-[var(--surface)] tw-p-4 tw-shadow-sm">
      <DataTable value={page?.items || []} dataKey="id" lazy paginator first={page?.offset || 0} rows={50} totalRecords={page?.total || 0} onPage={pageChanged} loading={loading} size="small" stripedRows
        paginatorTemplate="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink CurrentPageReport" currentPageReportTemplate="{first}–{last} de {totalRecords}"
        emptyMessage="No hay tiempos de arribo para los filtros seleccionados" className="tw-min-w-0 tw-max-w-full tw-text-[13px] [&_.p-datatable-table]:tw-table-fixed [&_td]:tw-h-9 [&_td]:tw-px-2 [&_td]:tw-py-1 [&_td]:tw-whitespace-normal [&_td]:tw-break-words [&_th]:tw-px-2 [&_th]:tw-py-1">
        <Column field="service" header="Servicio" headerClassName={headerClass} bodyClassName="tw-whitespace-normal tw-break-words" style={{ width: '15%' }} />
        <Column field="department" header="Departamento" headerClassName={headerClass} bodyClassName="tw-whitespace-normal tw-break-words" style={{ width: '21%' }} />
        <Column field="zone" header="Zona" headerClassName={headerClass} bodyClassName="tw-whitespace-normal tw-break-words" style={{ width: '25%' }} />
        <Column header="Tiempo base" body={row => <span className="tw-whitespace-nowrap">{row.base_estimated_minutes} min</span>} style={{ width: '14%' }} />
        <Column header="Estado" body={row => <Tag value={row.is_active ? 'Activo' : 'Inactivo'} severity={row.is_active ? 'success' : 'secondary'} />} style={{ width: '12%' }} />
        {model.canManage && <Column header="Acciones" body={row => <div className="tw-flex tw-w-full tw-flex-wrap tw-items-center tw-gap-1">
          <Button icon="pi pi-pencil" aria-label={`Editar ${row.service} en ${row.zone}`} text size="small" className="tw-h-8 tw-w-8" onClick={() => open(row)} />
          {row.is_active && <Button icon="pi pi-ban" aria-label={`Desactivar ${row.service} en ${row.zone}`} text severity="danger" size="small" className="tw-h-8 tw-w-8" onClick={() => setDeactivateCandidate(row)} />}
        </div>} style={{ width: '13%' }} />}
      </DataTable>
    </section>

    <Dialog header={editingId ? 'Editar tiempo de arribo' : 'Nuevo tiempo de arribo'} visible={visible} onHide={() => close()} modal appendTo={document.body} style={{ width: 'min(560px, 96vw)' }} breakpoints={{ '640px': '96vw' }}>
      <form onSubmit={save} className="tw-flex tw-flex-col tw-gap-3 tw-p-1">
        {conflict&&<div role="alert" className="tw-rounded-md tw-border tw-border-amber-400 tw-bg-amber-50 tw-p-3 tw-text-[13px]"><strong>El catálogo cambió mientras trabajabas.</strong><p className="tw-mb-2">Tu borrador permanece en el formulario. Compará los valores antes de continuar.</p>{conflictCurrent?<div className="tw-grid tw-gap-1"><span><strong>Versión vigente:</strong> {conflictCurrent.service} · {conflictCurrent.department} · {conflictCurrent.zone} · {conflictCurrent.base_estimated_minutes} min · {conflictCurrent.is_active?'Activo':'Inactivo'} (revisión {conflictCurrent.revision})</span><span><strong>Tu borrador:</strong> {form.service} · {form.department} · {form.zone} · {form.base_estimated_minutes} min · {form.is_active?'Activo':'Inactivo'}</span></div>:<span>No se pudo confirmar aún la versión vigente.</span>}<div className="tw-mt-2 tw-flex tw-flex-wrap tw-gap-2"><Button type="button" text size="small" label="Consultar versión vigente" onClick={()=>loadCurrentVersion(editingId,form,dialogSequence.current)} />{conflictCurrent&&<Button type="button" outlined size="small" label="Cargar versión vigente" onClick={adoptCurrent} />}</div></div>}
        {field('Servicio', <Dropdown appendTo={document.body} value={form.service} options={asOptions(services)} placeholder="Seleccioná un servicio" onChange={event => setForm(previous => ({ ...previous, service: event.value, department: '', zone: ALL_DEPARTMENT }))} className="tw-w-full" />)}
        {field('Departamento', <Dropdown appendTo={document.body} value={form.department} options={asOptions(Object.keys(departments))} placeholder="Seleccioná un departamento" disabled={!form.service} onChange={event => setForm(previous => ({ ...previous, department: event.value, zone: ALL_DEPARTMENT }))} className="tw-w-full" />)}
        {field('Zona', <Dropdown appendTo={document.body} value={form.zone} options={asOptions(zones)} disabled={!form.department} onChange={event => change('zone', event.value)} className="tw-w-full" />)}
        {field('Tiempo base (minutos)', <InputNumber value={form.base_estimated_minutes} onValueChange={event => change('base_estimated_minutes', event.value)} min={1} max={1440} useGrouping={false} className="tw-w-full" inputClassName="tw-w-full" />)}
        <label className="tw-flex tw-items-center tw-gap-3 tw-text-[13px] tw-font-medium"><InputSwitch checked={form.is_active} onChange={event => change('is_active', event.value)} />Activo</label>
        <div className="tw-flex tw-w-full tw-flex-wrap tw-items-center tw-justify-end tw-gap-3">
          <Button type="button" label="Cancelar" text size="small" onClick={() => close()} disabled={saving} />
          <Button type="submit" label="Guardar" icon="pi pi-check" size="small" loading={saving} disabled={saving || conflict} />
        </div>
      </form>
    </Dialog>
    <Dialog header="Desactivar tiempo de arribo" visible={Boolean(deactivateCandidate)} onHide={()=>setDeactivateCandidate(null)} modal appendTo={document.body} style={{ width: 'min(460px, 95vw)' }}>
      <p className="tw-m-0 tw-whitespace-normal tw-break-words">¿Desactivar {deactivateCandidate?.service} en {deactivateCandidate?.department} · {deactivateCandidate?.zone}? El registro permanecerá en el historial.</p>
      <div className="tw-mt-4 tw-flex tw-w-full tw-flex-wrap tw-items-center tw-justify-end tw-gap-3"><Button type="button" label="Cancelar" text size="small" onClick={()=>setDeactivateCandidate(null)} /><Button type="button" label="Desactivar" severity="danger" size="small" onClick={()=>deactivate(deactivateCandidate)} /></div>
    </Dialog>
  </div>;
}
