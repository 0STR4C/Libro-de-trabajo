import React, { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Calendar } from 'primereact/calendar';
import { Card } from 'primereact/card';
import { Column } from 'primereact/column';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { DataTable } from './dense-table.jsx';

const initialForm = () => ({ requested_date: '', request_type: 'AUSENCIA', reason: '', requested_start: null, requested_end: null });
const asDate = value => value ? new Date(`${String(value).slice(0, 10)}T12:00:00`) : null;
const iso = value => value ? `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}` : '';

export function ScheduleRequestsView({ model }) {
  const [requests, setRequests] = useState(model.requests || []);
  const [form, setForm] = useState(initialForm);
  const [open, setOpen] = useState(false);
  const [cancelTarget, setCancelTarget] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const flight = useRef(false);

  useEffect(() => { setRequests(model.requests || []); }, [model.requests]);
  const refresh = async () => setRequests(await model.request('/api/wfm/requests?scope=mine'));
  const submit = async event => {
    event.preventDefault();
    if (flight.current) return;
    flight.current = true; setBusy(true); setError('');
    try {
      await model.request('/api/wfm/requests', { method: 'POST', body: JSON.stringify(form) });
      await refresh(); setOpen(false); setForm(initialForm());
    } catch (failure) { setError(failure.message); }
    finally { flight.current = false; setBusy(false); }
  };
  const cancel = async () => {
    if (!cancelTarget || flight.current) return;
    const requestId = cancelTarget.request_id;
    flight.current = true; setBusy(true); setError(''); setCancelTarget(null);
    try {
      await model.request('/api/wfm/requests', { method: 'POST', body: JSON.stringify({ operation: 'cancel', request_id: requestId }) });
      await refresh();
    } catch (failure) {
      setError(failure.message);
      if (failure.payload?.detail?.code === 'WFM_REQUEST_ALREADY_RESOLVED') refresh().catch(() => {});
    } finally { flight.current = false; setBusy(false); }
  };

  return <div className="tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]">
    <Card className="tw-rounded-md tw-border tw-border-app-border tw-bg-app-surface tw-shadow-sm">
      <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-3">
        <span className="tw-text-app-muted">Consultá el estado y la resolución de tus pedidos.</span>
        <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-3">
          <Button label="Ver mis horarios" icon="pi pi-calendar" text size="small" onClick={model.onOpenSchedules} />
          <Button label="Nueva solicitud" icon="pi pi-plus" size="small" onClick={() => { setError(''); setOpen(true); }} />
        </div>
      </div>
    </Card>
    {error && <p role="alert" className="tw-text-red-700">{error}</p>}
    <Card className="tw-min-w-0 tw-rounded-md tw-border tw-border-app-border tw-bg-app-surface tw-shadow-sm" pt={{ body: { className: 'tw-p-0' }, content: { className: 'tw-p-0' } }}>
      <DataTable value={requests} dataKey="request_id" paginator rows={50} emptyMessage="Todavía no hay solicitudes">
        <Column field="requested_date" header="Fecha" className="tw-whitespace-nowrap" />
        <Column header="Tipo" body={item => item.request_type === 'CAMBIO_TURNO' ? 'Cambio de turno' : 'Ausencia'} />
        <Column field="reason" header="Motivo" className="tw-whitespace-normal tw-break-words" />
        <Column field="status" header="Estado" />
        <Column header="Resolución" body={item => <span className="tw-whitespace-normal tw-break-words">{item.resolution_note || '—'}{item.resolved_by ? ` · ${item.resolved_by}` : ''}</span>} />
        <Column header="Acción" body={item => item.status === 'PENDIENTE' && <Button label="Cancelar" text severity="danger" size="small" disabled={busy} onClick={() => setCancelTarget(item)} />} />
      </DataTable>
    </Card>
    <Dialog header="Nueva solicitud" visible={open} onHide={() => setOpen(false)} modal appendTo={document.body} style={{ width: 'min(560px, 95vw)' }}>
      <form onSubmit={submit} className="tw-grid tw-gap-3">
        <label className="tw-grid tw-gap-1">Fecha<Calendar appendTo={document.body} value={asDate(form.requested_date)} onChange={event => setForm(current => ({ ...current, requested_date: iso(event.value) }))} dateFormat="dd/mm/yy" showIcon required /></label>
        <label className="tw-grid tw-gap-1">Tipo<Dropdown appendTo={document.body} value={form.request_type} options={[{ label: 'Ausencia', value: 'AUSENCIA' }, { label: 'Cambio de turno', value: 'CAMBIO_TURNO' }]} onChange={event => setForm(current => ({ ...current, request_type: event.value }))} /></label>
        {form.request_type === 'CAMBIO_TURNO' && <div className="tw-grid tw-gap-3 sm:tw-grid-cols-2">
          <label className="tw-grid tw-gap-1">Inicio solicitado (franja de 30 min)<InputText type="number" min="0" max="47" value={form.requested_start ?? ''} onChange={event => setForm(current => ({ ...current, requested_start: event.target.value === '' ? null : Number(event.target.value) }))} required /></label>
          <label className="tw-grid tw-gap-1">Fin solicitado (franja de 30 min)<InputText type="number" min="1" max="72" value={form.requested_end ?? ''} onChange={event => setForm(current => ({ ...current, requested_end: event.target.value === '' ? null : Number(event.target.value) }))} required /></label>
        </div>}
        <label className="tw-grid tw-gap-1">Motivo<InputTextarea value={form.reason} onChange={event => setForm(current => ({ ...current, reason: event.target.value }))} minLength={3} maxLength={500} required /></label>
        {error && <p role="alert" className="tw-text-red-700">{error}</p>}
        <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-end tw-gap-3"><Button label="Cerrar" text type="button" onClick={() => setOpen(false)} /><Button label="Enviar solicitud" type="submit" loading={busy} /></div>
      </form>
    </Dialog>
    <Dialog header="Cancelar solicitud" visible={Boolean(cancelTarget)} onHide={() => setCancelTarget(null)} modal appendTo={document.body} style={{ width: 'min(480px, 95vw)' }}>
      <p>¿Cancelar la solicitud pendiente del {cancelTarget?.requested_date || ''}?</p>
      <div className="tw-mt-3 tw-flex tw-flex-wrap tw-items-center tw-justify-end tw-gap-3"><Button label="Conservar" text onClick={() => setCancelTarget(null)} /><Button label="Cancelar solicitud" severity="danger" loading={busy} onClick={cancel} /></div>
    </Dialog>
  </div>;
}
