import React, { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Calendar } from 'primereact/calendar';
import { Card } from 'primereact/card';
import { Column } from 'primereact/column';
import { DataTable } from './dense-table.jsx';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { formatDateTime } from './date-format.js';
import { displayLocation, displayService } from './operational-labels.js';

const stamp = formatDateTime;
const toDate = value => value ? new Date(`${value}T12:00:00`) : null;
const fromDate = value => value ? `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}` : '';

export function DelayAuditView({ model, active = true }) {
  const [filters,setFilters]=useState(model.filters),[page,setPage]=useState(model.page),[selected,setSelected]=useState(null),[events,setEvents]=useState([]),[error,setError]=useState('');
  const [loading,setLoading]=useState(false),activeRef=useRef(active);
  activeRef.current=active;
  const pageSequence=useRef(0);
  useEffect(()=>()=>{pageSequence.current+=1;},[]);
  useEffect(()=>{if(!active){pageSequence.current+=1;setLoading(false);}},[active]);
  useEffect(()=>setFilters(model.filters),[model.filters]);
  useEffect(()=>{pageSequence.current+=1;setError('');setPage(model.page);},[model.page]);
  const change=(key,value)=>setFilters(current=>({...current,[key]:value}));
  const apply=()=>{pageSequence.current+=1;setLoading(false);return model.onApply(filters);};
  const clear=()=>{pageSequence.current+=1;setLoading(false);return model.onClear();};
  const turnPage=async (offset,limit)=>{const sequence=++pageSequence.current;setError('');setLoading(true);try{const result=await model.onPage(offset,limit);if(sequence===pageSequence.current&&activeRef.current)setPage(result);}catch(failure){if(sequence===pageSequence.current&&activeRef.current&&!failure.stale)setError(failure.message);}finally{if(sequence===pageSequence.current)setLoading(false);}};
  const history=async row=>{setError('');try{setEvents(await model.request(`/api/delays/${row.id}/events`));setSelected(row);}catch(failure){setError(failure.message);}};
  return <div className="operational-view tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]">
    <Card title="Auditoría histórica de demoras" className="tw-min-w-0 tw-shadow-sm" pt={{body:{className:'tw-p-3'}}}>
      <div className="tw-flex tw-flex-wrap tw-items-end tw-gap-3 tw-w-full">
        <label className="tw-grid tw-gap-1">Desde<Calendar appendTo={document.body} value={toDate(filters.from)} onChange={event=>change('from',fromDate(event.value))} dateFormat="dd/mm/yy" showIcon /></label>
        <label className="tw-grid tw-gap-1">Hasta<Calendar appendTo={document.body} value={toDate(filters.to)} onChange={event=>change('to',fromDate(event.value))} dateFormat="dd/mm/yy" showIcon /></label>
        <label className="tw-grid tw-gap-1">Estado<Dropdown appendTo={document.body} value={filters.scope} options={[{label:'Todas',value:'all'},{label:'Normalizadas',value:'normalized'},{label:'Vigentes',value:'current'},{label:'Requieren revisión',value:'review'}]} onChange={event=>change('scope',event.value)}/></label>
        <label className="tw-grid tw-gap-1">Departamento<Dropdown appendTo={document.body} value={filters.department} options={model.departments} filter onChange={event=>change('department',event.value)}/></label>
        <label className="tw-grid tw-gap-1">Zona o agente<InputText value={filters.search} onChange={event=>change('search',event.target.value)} onKeyDown={event=>event.key==='Enter'&&apply()}/></label>
        <Button label="Aplicar filtros" onClick={apply}/><Button label="Limpiar" text onClick={clear}/>
      </div>
    </Card>
    {error&&<p role="alert" className="tw-text-red-700">{error}</p>}
    <Card className="tw-min-w-0 tw-shadow-sm" pt={{body:{className:'tw-p-0'},content:{className:'tw-p-0'}}}>
      <DataTable value={page.items} dataKey="id" lazy paginator loading={loading} rows={page.limit||50} first={page.offset} totalRecords={page.total} onPage={event=>turnPage(event.rows===page.limit?event.first:0,event.rows)} emptyMessage="No hay demoras para los filtros seleccionados" scrollable>
        <Column field="department" header="Departamento" body={row=>displayLocation(row.department)}/><Column field="zone" header="Zona" className="tw-whitespace-normal tw-break-words" body={row=>displayLocation(row.zone)}/>
        <Column field="service" header="Prestación" body={row=>displayService(row.service)}/><Column header="Registrada" className="tw-whitespace-nowrap" body={row=>stamp(row.created_at)}/>
        <Column field="agent" header="Registró"/><Column header="Retirada" className="tw-whitespace-nowrap" body={row=>stamp(row.normalized_at)}/>
        <Column header="Retiró" body={row=>row.normalized_by||'—'}/><Column header="Estado" body={row=><Tag value={row.status==='NORMALIZADO'?'Normalizada':row.needs_review?'Revisión pendiente':'Vigente'} severity={row.status==='NORMALIZADO'?'success':row.needs_review?'warning':'info'}/>}/>
        <Column header="Trazabilidad" body={row=><Button label="Ver eventos" icon="pi pi-history" text size="small" onClick={()=>history(row)}/>}/>
      </DataTable>
    </Card>
    <Dialog header={selected?`${displayLocation(selected.department)} · ${displayLocation(selected.zone)}`:'Trazabilidad'} visible={Boolean(selected)} onHide={()=>setSelected(null)} modal appendTo={document.body} style={{width:'min(680px,95vw)'}}>
      {selected&&<div className="tw-grid tw-gap-2"><p><strong>Alta:</strong> {stamp(selected.created_at)} · {selected.agent}</p><p><strong>Retiro:</strong> {stamp(selected.normalized_at)} · {selected.normalized_by||'—'}</p>{selected.resolution_note&&<p><strong>Motivo de cierre:</strong> {selected.resolution_note}</p>}</div>}
      <div className="tw-grid tw-gap-2">{events.map(event=><div key={event.id} className="tw-rounded-md tw-border tw-border-slate-200 tw-p-3"><strong>{event.event_type}</strong><span className="tw-ml-2">{stamp(event.created_at)} · {event.actor}</span>{event.note&&<p className="tw-mb-0">{event.note}</p>}</div>)}</div>
    </Dialog>
  </div>;
}
