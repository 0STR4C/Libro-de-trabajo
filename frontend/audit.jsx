import React, { useEffect, useState } from 'react';
import { Button } from 'primereact/button';
import { Calendar } from 'primereact/calendar';
import { Card } from 'primereact/card';
import { Column } from 'primereact/column';
import { DataTable } from './dense-table.jsx';
import { InputText } from 'primereact/inputtext';

const changes = row => {
  try {
    const before = row.before_data ? JSON.parse(row.before_data) : null;
    const after = row.after_data ? JSON.parse(row.after_data) : null;
    if (!before && !after) return row.detail || '—';
    const keys = [...new Set([...Object.keys(before || {}), ...Object.keys(after || {})])].filter(key => JSON.stringify(before?.[key]) !== JSON.stringify(after?.[key]));
    return keys.length ? <div className="tw-grid tw-gap-1">{keys.slice(0, 6).map(key => <span key={key}><strong>{key}</strong>: {String(before?.[key] ?? '—')} → {String(after?.[key] ?? '—')}</span>)}</div> : row.detail || 'Sin diferencias';
  } catch { return row.detail || '—'; }
};
const date = value => value ? new Date(`${value}T12:00:00`) : null;
const iso = value => value ? `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}` : '';

export function AuditView({ model }) {
  const [filters, setFilters] = useState(model.filters);
  const [page, setPage] = useState(model.page);
  const [error, setError] = useState('');
  useEffect(() => setFilters(model.filters), [model.filters]);
  useEffect(() => setPage(model.page), [model.page]);
  const change = (key, value) => setFilters(current => ({ ...current, [key]: value }));
  const turnPage = async (offset, limit) => {
    setError('');
    try { setPage(await model.onPage(offset, limit)); }
    catch (failure) { setError(failure.message); }
  };
  return <div className="operational-view tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]">
    <Card title="Registro de auditoría" className="tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm">
      <p>{page.total} eventos</p>
      {model.canExport && <Button className="tw-h-9" label="Descargar esta vista" icon="pi pi-download" outlined size="small" onClick={model.onExport} />}
      <div className="tw-mt-3 tw-flex tw-flex-wrap tw-items-end tw-gap-4">
        {[['from','Desde'],['to','Hasta']].map(([key,label]) => <label key={key}>{label}<Calendar appendTo={document.body} className="tw-block tw-h-9" value={date(filters[key])} onChange={event => change(key, iso(event.value))} dateFormat="dd/mm/yy" showIcon /></label>)}
        {[['entity','Tipo de registro'],['entityId','ID del registro'],['action','Acción exacta'],['actorId','ID de usuario'],['search','Usuario o detalle']].map(([key,label]) => <label key={key}>{label}<InputText className="tw-block tw-h-9" value={filters[key]} onChange={event => change(key,event.target.value)} onKeyDown={event => event.key === 'Enter' && model.onApply(filters)} /></label>)}
        <Button className="tw-h-9" label="Aplicar filtros" size="small" onClick={() => model.onApply(filters)} />
        <Button className="tw-h-9" label="Limpiar" text size="small" onClick={model.onClear} />
      </div>
    </Card>
    {error && <p role="alert" className="tw-text-red-700">{error}</p>}
    <Card className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm" pt={{ body:{ className:'tw-p-0' }, content:{ className:'tw-p-0' } }}>
      <DataTable value={page.items} dataKey="id" scrollable lazy paginator rows={page.limit || 50} first={page.offset} totalRecords={page.total} onPage={event => turnPage(event.rows === page.limit ? event.first : 0, event.rows)} emptyMessage="No hay eventos para los filtros seleccionados">
        <Column header="Fecha" className="tw-whitespace-nowrap" body={row => new Date(row.created_at).toLocaleString('es-UY')} />
        <Column header="Registro" body={row => `${row.entity} #${row.entity_id}`} />
        <Column field="action" header="Acción" />
        <Column header="Usuario" body={row => row.actor_name || row.actor} />
        <Column header="Cambios" className="operational-long-text" style={{ minWidth:'250px', whiteSpace:'normal', wordWrap:'break-word' }} body={changes} />
        <Column header="Origen" body={row => row.source || 'web'} />
      </DataTable>
    </Card>
  </div>;
}
