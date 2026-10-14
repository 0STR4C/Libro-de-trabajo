import React, { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Calendar } from 'primereact/calendar';
import { Card } from 'primereact/card';
import { Checkbox } from 'primereact/checkbox';
import { Column } from 'primereact/column';
import { DataTable } from './dense-table.jsx';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { createWfmRequestCoordinator, wfmResponseMatches } from './wfm-request-coordinator.js';

const teams = ['Telefonista', 'Planificador', 'Supervisor'];
const weekdays = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
const iso = value => value ? `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}` : '';
const date = value => value ? new Date(`${value}T12:00:00`) : null;
const clock = slot => slot == null ? '—' : `${String(Math.floor(Number(slot) / 2) % 24).padStart(2, '0')}:${Number(slot) % 2 ? '30' : '00'}${Number(slot) >= 48 ? ' +1' : ''}`;
const operationalAt = (shift, slot) => {
  const segments = shift.segments?.length ? shift.segments : [{ start: shift.start, end: shift.end }];
  return segments.some(segment => segment.start <= slot && slot < segment.end)
    && !(shift.break != null && (shift.break_duration ?? 1) > 0 && shift.break <= slot && slot < shift.break + (shift.break_duration ?? 1))
    && !(shift.exceptions || []).some(exception => exception.start <= slot && slot < exception.end);
};

function WfmTimeline({ plan, onMove, onEdit, onMeeting }) {
  const shifts = plan.shifts || [];
  const segments = shifts.flatMap(shift => shift.segments?.length ? shift.segments : [{ start: shift.start, end: shift.end }]);
  const first = Math.min(plan.window?.[0] ?? 0, ...segments.map(item => item.start));
  const last = Math.max(plan.window?.[1] ?? 48, ...segments.map(item => item.end));
  const span = Math.max(1, last - first);
  const place = (start, end, top, color) => ({ position: 'absolute', left: `${(start - first) / span * 100}%`, width: `${Math.max(1, (end - start) / span * 100)}%`, top, height: 19, background: color, borderRadius: 4, color: 'white', overflow: 'hidden', whiteSpace: 'nowrap', fontSize: 11, cursor: 'grab' });
  const begin = (event, kind, shift, index, start, end) => {
    event.stopPropagation();
    const rect = event.currentTarget.getBoundingClientRect();
    const offset = Math.max(0, Math.min(end - start - 1, Math.floor((event.clientX - rect.left) / Math.max(1, rect.width) * (end - start))));
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('application/json', JSON.stringify({ kind, userId: shift.user_id, index, offset }));
  };
  const drop = (event, shift) => {
    event.preventDefault();
    try {
      const item = JSON.parse(event.dataTransfer.getData('application/json'));
      if (Number(item.userId) !== Number(shift.user_id)) return;
      const rect = event.currentTarget.getBoundingClientRect();
      const slot = first + Math.round((event.clientX - rect.left) / Math.max(1, rect.width) * span) - item.offset;
      onMove(item.kind, shift.user_id, item.index, slot);
    } catch { /* Ignorar datos de arrastre externos. */ }
  };
  return <DataTable stripedRows value={shifts} dataKey="user_id" size="small" scrollable emptyMessage="No hay turnos en el borrador"><Column header="Agente" frozen body={shift => plan.people?.find(person => person.id === shift.user_id)?.display_name || shift.user_id} /><Column header={`Línea de tiempo · ${clock(first)} a ${clock(last)}`} style={{ minWidth: '750px' }} body={shift => <div className="tw-relative tw-min-h-[76px] tw-rounded-md tw-border tw-bg-slate-50 dark:tw-bg-slate-900" onDragOver={event => event.preventDefault()} onDrop={event => drop(event, shift)} onContextMenu={event => { event.preventDefault(); onEdit(shift); }} onDoubleClick={() => onEdit(shift)}>{(shift.segments?.length ? shift.segments : [{ start: shift.start, end: shift.end }]).map((segment, index) => <div key={`segment-${index}`} draggable onDragStart={event => begin(event, 'segment', shift, index, segment.start, segment.end)} style={place(segment.start, segment.end, 5, '#2563eb')} title="Arrastrar bloque · clic derecho o doble clic para editar">{clock(segment.start)}–{clock(segment.end)}</div>)}{shift.break != null && (shift.break_duration ?? 1) > 0 && <div draggable onDragStart={event => begin(event, 'break', shift, 0, shift.break, shift.break + (shift.break_duration ?? 1))} style={place(shift.break, shift.break + (shift.break_duration ?? 1), 29, '#d97706')} title="Arrastrar descanso">Descanso</div>}{(shift.exceptions || []).map((exception, index) => <div key={exception.id || index} draggable onDragStart={event => begin(event, 'exception', shift, index, exception.start, exception.end)} style={place(exception.start, exception.end, 52, '#b91c1c')} title="Arrastrar excepción · doble clic para editar"><span draggable onDragStart={event => begin(event, 'exception-start', shift, index, exception.start, exception.end)} aria-label="Mover inicio de excepción" style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 8, background: '#7f1d1d', cursor: 'ew-resize' }} />{exception.type}<span draggable onDragStart={event => begin(event, 'exception-end', shift, index, exception.start, exception.end)} aria-label="Mover fin de excepción" style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: 8, background: '#7f1d1d', cursor: 'ew-resize' }} /></div>)}</div>} /><Column header="Acción" frozen alignFrozen="right" body={shift => <div className="tw-flex tw-gap-1"><Button className="tw-h-9" label="Editar" text size="small" onClick={() => onEdit(shift)} /><Button className="tw-h-9" label="Reunión 30 min" text size="small" onClick={() => onMeeting(shift)} /></div>} /></DataTable>;
}

export function WfmView({ model }) {
  const [day, setDay] = useState(model.day);
  const [team, setTeam] = useState(model.team);
  const [plan, setPlan] = useState(model.plan);
  const [isLoading, setIsLoading] = useState(false);
  const lastLoaded = useRef({day:model.day,team:model.team});
  const [dirty, setDirty] = useState(false);
  const [requirementsDirty, setRequirementsDirty] = useState(false);
  const [operation, setOperation] = useState('');
  const [confirmation, setConfirmation] = useState(null);
  const [navigationIntent, setNavigationIntent] = useState(null);
  const [requestFilter, setRequestFilter] = useState('PENDIENTE');
  const [requestType, setRequestType] = useState('');
  const [requestFrom, setRequestFrom] = useState('');
  const [requestTo, setRequestTo] = useState('');
  const [requestPerson, setRequestPerson] = useState('');
  const [requestSearch, setRequestSearch] = useState('');
  const [requests, setRequests] = useState(model.requests || []);
  const [decision, setDecision] = useState(null);
  const [decisionNote, setDecisionNote] = useState('');
  const [shiftEditor, setShiftEditor] = useState(null);
  const [inspectPersonId, setInspectPersonId] = useState('');
  const [personWeek, setPersonWeek] = useState(null);
  const toast = useRef(null);
  const coordinator = useRef(createWfmRequestCoordinator({ day: model.day, team: model.team, revision: model.plan.revision }));
  const current = useRef({ day, team, plan, dirty: dirty || requirementsDirty });
  current.current = { day, team, plan, dirty: dirty || requirementsDirty };
  const busy = Boolean(operation);
  const notify = (severity, detail) => toast.current?.show({ severity, summary: severity === 'error' ? 'Error' : 'Listo', detail, life: 4500 });
  const update = next => { coordinator.current.markEdited(); setPlan(next); setDirty(true); };
  const shiftChange = (userId, key, value) => update({ ...plan, shifts: plan.shifts.map(shift => shift.user_id === userId ? { ...shift, [key]: value, ...(key === 'start' || key === 'end' ? { segments: [{ start: key === 'start' ? value : shift.start, end: key === 'end' ? value : shift.end }] } : {}) } : shift) });
  const beginOperation = kind => {
    const token = coordinator.current.beginMutation(kind);
    if (!token) return null;
    setOperation(kind);
    return token;
  };
  const finishOperation = token => {
    coordinator.current.finishMutation(token);
    if (!coordinator.current.pendingMutation) setOperation('');
  };
  const performLoad = async (nextDay, nextTeam) => {
    setNavigationIntent(null);
    const token = coordinator.current.beginLoad(nextDay, nextTeam);
    setDay(nextDay); setTeam(nextTeam); setIsLoading(true);
    try {
      const [nextPlan, nextRequests] = await Promise.all([
        model.request(`/api/wfm/plan?date=${nextDay}&team=${encodeURIComponent(nextTeam)}`),
        model.request(`/api/wfm/requests?team=${encodeURIComponent(nextTeam)}`).catch(() => []),
      ]);
      if (!coordinator.current.isLoadCurrent(token) || !wfmResponseMatches(nextPlan, token)) return false;
      coordinator.current.acceptLoad(token, nextPlan.revision);
      lastLoaded.current = { day: nextDay, team: nextTeam };
      React.startTransition(() => { setPlan(nextPlan); setRequests(nextRequests); setDirty(false); setRequirementsDirty(false); setIsLoading(false); });
      return true;
    } catch (error) {
      if (!coordinator.current.isLoadCurrent(token)) return false;
      setDay(lastLoaded.current.day); setTeam(lastLoaded.current.team); setIsLoading(false);
      if (!error.stale) notify('error', error.message);
      return false;
    }
  };
  const load = (nextDay = current.current.day, nextTeam = current.current.team, force = false) => {
    if (!force && (current.current.dirty || coordinator.current.pendingMutation)) {
      setNavigationIntent({ day: nextDay, team: nextTeam });
      return Promise.resolve(false);
    }
    return performLoad(nextDay, nextTeam);
  };
  const send = async (kind, confirmed = false) => {
    if (kind === 'publish' && !confirmed) {
      setConfirmation({
        title: 'Publicar planificación del día',
        message: `Se publicará ${current.current.day} para ${current.current.team} y se confirmarán sus advertencias operativas.`,
        acceptLabel: 'Publicar día',
        accept: () => send('publish', true),
      });
      return false;
    }
    const token = beginOperation(kind);
    if (!token) return false;
    const source = current.current.plan;
    try {
      const payload = { revision: token.revision, demand: source.demand, shifts: source.shifts, operation: kind, confirm_exceptions: kind === 'publish' };
      const result = await model.request(`/api/wfm/plan?date=${token.day}&team=${encodeURIComponent(token.team)}`, { method: 'POST', body: JSON.stringify(payload) });
      if (wfmResponseMatches(result, token) && coordinator.current.acceptMutation(token, result.revision)) {
        setPlan(result);
        if (kind === 'optimize') coordinator.current.markEdited();
        setDirty(kind === 'optimize');
      }
      notify('success', `${kind === 'save' ? 'Borrador guardado' : kind === 'publish' ? 'Día publicado' : 'Descansos sugeridos'} · ${token.day} · ${token.team}`);
      return true;
    } catch (error) {
      if (!error.stale) notify('error', error.message);
      return false;
    } finally { finishOperation(token); }
  };
  const addPerson = userId => { const person = plan.people.find(item => item.id === Number(userId)); if (!person || plan.shifts.some(shift => shift.user_id === person.id)) return; const template = (plan.weekly_schedule || []).find(item => item.user_id === person.id); const start = template?.start ?? plan.window?.[0] ?? 16, end = template?.end ?? start + (plan.settings?.shift_slots || 13); const duration = plan.settings?.break_slots || 1; update({ ...plan, shifts: [...plan.shifts, { user_id: person.id, start, end, segments: [{ start, end }], break: template?.break_slot ?? start + Math.floor((end - start) / 2), break_duration: duration, overtime_slots: 0, exceptions: [], locked: false }] }); };
  const removePerson = userId => update({ ...plan, shifts: plan.shifts.filter(item => item.user_id !== userId) });
  const editShift = value => setShiftEditor({ ...value, segments: (value.segments || []).map(item => ({ ...item })), exceptions: (value.exceptions || []).map(item => ({ ...item })) });
  const moveTimeline = (kind, userId, index, proposed) => {
    const shift = plan.shifts.find(item => item.user_id === userId);
    if (!shift) return;
    const segments = shift.segments?.length ? shift.segments : [{ start: shift.start, end: shift.end }];
    let next = shift;
    if (kind === 'segment') {
      const segment = segments[index]; if (!segment) return;
      const duration = segment.end - segment.start;
      const windowStart = plan.window?.[0] ?? 0, windowEnd = plan.window?.[1] ?? 72;
      const start = Math.max(windowStart, Math.min(windowEnd - duration, proposed));
      const end = start + duration;
      if (index === 0 && start >= 48 || segments.some((item, position) => position !== index && item.start < end && start < item.end)) { notify('error', 'El bloque debe quedar libre y dentro del horizonte'); return; }
      const delta = start - segment.start;
      const moved = segments.map((item, position) => position === index ? { start, end } : item).sort((a, b) => a.start - b.start);
      next = { ...shift, segments: moved, start: moved[0].start, end: moved.at(-1).end,
        break: shift.break != null && segment.start <= shift.break && shift.break < segment.end ? shift.break + delta : shift.break,
        exceptions: (shift.exceptions || []).map(item => segment.start <= item.start && item.end <= segment.end ? { ...item, start: item.start + delta, end: item.end + delta } : item) };
    } else if (kind === 'break') {
      const duration = shift.break_duration ?? 1;
      const start = Math.max(0, Math.min(72 - duration, proposed));
      if (!segments.some(item => item.start <= start && start + duration <= item.end)) { notify('error', 'El descanso debe quedar dentro de un bloque'); return; }
      next = { ...shift, break: start };
    } else if (kind === 'exception') {
      const exception = shift.exceptions?.[index]; if (!exception) return;
      const duration = exception.end - exception.start;
      const start = Math.max(0, Math.min(72 - duration, proposed));
      if (!segments.some(item => item.start <= start && start + duration <= item.end)) { notify('error', 'La excepción debe quedar dentro de un bloque'); return; }
      next = { ...shift, exceptions: shift.exceptions.map((item, position) => position === index ? { ...item, start, end: start + duration } : item) };
    } else if (kind === 'exception-start' || kind === 'exception-end') {
      const exception = shift.exceptions?.[index]; if (!exception) return;
      const start = kind === 'exception-start' ? Math.max(0, Math.min(proposed, exception.end - 1)) : exception.start;
      const end = kind === 'exception-end' ? Math.min(72, Math.max(proposed, exception.start + 1)) : exception.end;
      if (!segments.some(item => item.start <= start && end <= item.end)) { notify('error', 'La excepción debe quedar dentro de un bloque'); return; }
      next = { ...shift, exceptions: shift.exceptions.map((item, position) => position === index ? { ...item, start, end } : item) };
    }
    if (next !== shift) update({ ...plan, shifts: plan.shifts.map(item => item.user_id === userId ? next : item) });
  };
  const addMeeting = shift => {
    const segment = shift.segments?.[0] || { start: shift.start, end: shift.end };
    if (!segment || segment.end <= segment.start) return;
    const start = Math.min(segment.start + 2, segment.end - 1);
    const exception = { id: `manual-${Date.now()}`, type: 'Reunión', start, end: start + 1, note: '' };
    update({ ...plan, shifts: plan.shifts.map(item => item.user_id === shift.user_id ? { ...item, exceptions: [...(item.exceptions || []), exception] } : item) });
  };
  const editSegment = (index, key, value) => setShiftEditor(current => ({ ...current, segments: current.segments.map((item, position) => position === index ? { ...item, [key]: value } : item) }));
  const editException = (index, key, value) => setShiftEditor(current => ({ ...current, exceptions: current.exceptions.map((item, position) => position === index ? { ...item, [key]: value } : item) }));
  const saveShiftEditor = () => { const segments = shiftEditor.segments.slice().sort((a, b) => a.start - b.start); if (!segments.length || segments.some(item => item.start == null || item.end == null || item.start >= item.end)) { notify('error', 'Revisá los bloques del turno'); return; } const next = { ...shiftEditor, segments, start: segments[0].start, end: segments.at(-1).end }; update({ ...plan, shifts: plan.shifts.map(item => item.user_id === next.user_id ? next : item) }); setShiftEditor(null); };
  const saveRequirements = async () => {
    const token = beginOperation('requirements');
    if (!token) return false;
    const source = current.current.plan;
    try {
      const saved = await model.request(`/api/wfm/requirements?team=${encodeURIComponent(token.team)}`, { method: 'POST', body: JSON.stringify({ requirements: source.requirements, expected_revision: source.requirements_revision }) });
      if (coordinator.current.acceptMutation(token, token.revision) && saved.team === token.team) {
        setPlan(value => ({ ...value, requirements_revision: saved.revision }));
        setRequirementsDirty(false);
      }
      notify('success', `Requerimientos actualizados · ${token.team}`);
      return true;
    } catch (error) { if (!error.stale) notify('error', error.message); return false; }
    finally { finishOperation(token); }
  };
  const weekStart = value => { const result = date(value); result.setDate(result.getDate() - (result.getDay() + 6) % 7); return iso(result); };
  const weekDays = Array.from({ length: 7 }, (_, index) => { const value = date(weekStart(day)); value.setDate(value.getDate() + index); return iso(value); });
  const inspectWeek = async () => { if (!inspectPersonId) return; const from = weekStart(day); const toDate = date(from); toDate.setDate(toDate.getDate() + 6); try { setPersonWeek(await model.request(`/api/wfm/person?from=${from}&to=${iso(toDate)}&team=${encodeURIComponent(team)}&user_id=${inspectPersonId}`)); } catch (error) { notify('error', error.message); } };
  const moveWeek = offset => { const result = date(weekStart(day)); result.setDate(result.getDate() + offset); load(iso(result), team); };
  const executeWeekPublish = async (token, start, expectedRevisions) => {
    try {
      const result = await model.request(`/api/wfm/publish-week?week=${start}&team=${encodeURIComponent(token.team)}`, { method: 'POST', body: JSON.stringify({ expected_revisions: expectedRevisions, confirm_exceptions: true }) });
      notify('success', `${result.published_count} días publicados · ${start} · ${token.team}`);
      const stillHere = coordinator.current.isMutationCurrent(token);
      finishOperation(token);
      if (stillHere) await load(current.current.day, current.current.team, true);
      return true;
    } catch (error) {
      if (!error.stale) notify('error', error.message);
      finishOperation(token);
      return false;
    }
  };
  const publishWeek = async () => {
    if (current.current.dirty) { notify('error', 'Guardá el borrador y los requerimientos antes de publicar la semana'); return false; }
    const token = beginOperation('publish-week');
    if (!token) return false;
    const start = weekStart(token.day);
    const days = Array.from({ length: 7 }, (_, index) => { const value = date(start); value.setDate(value.getDate() + index); return iso(value); });
    try {
      const plans = await Promise.all(days.map(value => model.request(`/api/wfm/plan?date=${value}&team=${encodeURIComponent(token.team)}`)));
      if (!coordinator.current.isMutationCurrent(token) || plans.some((item, index) => !wfmResponseMatches(item, { day: days[index], team: token.team }))) { finishOperation(token); return false; }
      const expectedRevisions = Object.fromEntries(days.map((value, index) => [value, plans[index].revision || 0]));
      const review = days.map((value, index) => `${value}: ${(plans[index].warnings || []).length ? plans[index].warnings.join('; ') : 'sin advertencias'}`).join('\n');
      setConfirmation({
        title: 'Publicar semana completa',
        message: `Semana del ${start}\n\n${review}`,
        acceptLabel: 'Publicar semana',
        accept: () => executeWeekPublish(token, start, expectedRevisions),
        cancel: () => finishOperation(token),
      });
      return true;
    } catch (error) {
      if (!error.stale) notify('error', error.message);
      finishOperation(token);
      return false;
    }
  };
  const decideRequest = async (selected, note, confirmationRevision = null) => {
    const token = beginOperation('request-decision');
    if (!token) return false;
    const body = {
      operation: 'decide', request_id: selected.request_id, decision: selected.decision,
      resolution_note: note, confirm_current_revision: confirmationRevision != null,
      ...(confirmationRevision != null ? { expected_published_revision: confirmationRevision } : {}),
    };
    try {
      const result = await model.request('/api/wfm/requests', { method: 'POST', body: JSON.stringify(body) });
      const sameTeam = current.current.team === result.team;
      if (sameTeam) {
        const refreshed = await model.request(`/api/wfm/requests?team=${encodeURIComponent(result.team)}`);
        if (coordinator.current.isMutationCurrent(token)) setRequests(refreshed);
      }
      setDecision(null); setDecisionNote('');
      notify('success', `Solicitud ${result.status.toLocaleLowerCase('es-UY')}`);
      const reloadPlan = result.status === 'APROBADA' && current.current.day === result.requested_date && sameTeam && coordinator.current.isMutationCurrent(token);
      finishOperation(token);
      if (reloadPlan) await load(current.current.day, current.current.team, true);
      return true;
    } catch (error) {
      const detail = error.payload?.detail;
      finishOperation(token);
      if (error.status === 409 && detail?.code === 'WFM_REQUEST_SOURCE_REVISION_CONFLICT') {
        const conflict = detail.conflict;
        setConfirmation({
          title: 'El horario publicado cambió',
          message: `${detail.message}\n\nLa confirmación se aplicará únicamente sobre la revisión ${conflict.current_revision}.`,
          acceptLabel: selected.decision === 'APROBAR' ? 'Aprobar revisión vigente' : 'Confirmar',
          accept: () => decideRequest(selected, note, conflict.current_revision),
        });
        return false;
      }
      if (!error.stale) notify('error', error.message);
      if (detail?.code === 'WFM_REQUEST_ALREADY_RESOLVED' && current.current.team === selected.team) {
        model.request(`/api/wfm/requests?team=${encodeURIComponent(selected.team)}`).then(setRequests).catch(() => {});
      }
      return false;
    }
  };
  const decide = () => decision ? decideRequest({ ...decision }, decisionNote) : Promise.resolve(false);
  const coverage = (isLoading ? [] : plan.demand || []).map((required, slot) => {
    const operational = (plan.shifts || []).filter(shift => operationalAt(shift, slot)).length;
    const visible = !plan.window || plan.window[0] <= slot && slot < plan.window[1];
    return { required, operational, difference: visible && required != null ? operational - required : visible ? null : 0 };
  });
  const filteredRequests = (isLoading ? [] : requests).filter(item => (requestFilter === 'TODAS' || item.status === requestFilter)
    && (!requestType || item.request_type === requestType)
    && (!requestFrom || item.requested_date >= requestFrom)
    && (!requestTo || item.requested_date <= requestTo)
    && (!requestPerson || String(item.user_id) === requestPerson)
    && (!requestSearch || [item.display_name, item.requester_name, item.reason, item.request_type].some(value => String(value || '').toLocaleLowerCase('es-UY').includes(requestSearch.toLocaleLowerCase('es-UY')))));
  const [personId, setPersonId] = useState('');
  if(isLoading)return <div className="operational-view tw-grid tw-gap-3 tw-text-[13px]"><Toast ref={toast}/><Card title="Planificación de horarios" className="tw-shadow-sm"><div className="tw-flex tw-flex-wrap tw-items-center tw-gap-3"><strong>{team} · {day}</strong><Button label="Semana anterior" outlined size="small" onClick={()=>moveWeek(-7)}/><Button label="Semana siguiente" outlined size="small" onClick={()=>moveWeek(7)}/><Button label="Día anterior" text size="small" onClick={()=>{const next=date(day);next.setDate(next.getDate()-1);load(iso(next),team);}}/><Button label="Día siguiente" text size="small" onClick={()=>{const next=date(day);next.setDate(next.getDate()+1);load(iso(next),team);}}/></div><div role="status" className="tw-flex tw-items-center tw-gap-3 tw-p-4"><ProgressSpinner style={{width:28,height:28}} strokeWidth="5"/>Cargando planificación…</div></Card></div>;
  return <div className="operational-view wfm-react-view tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]"><Toast ref={toast} /><Card title="Planificación de horarios" className="tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><div className="tw-flex tw-flex-wrap tw-items-center tw-gap-3 tw-w-full tw-min-w-0"><label className="tw-grid tw-gap-1 tw-min-w-0 tw-max-w-full">Fecha<Calendar appendTo={document.body} className="tw-inline-flex tw-h-9 tw-w-full tw-min-w-0" inputClassName="tw-w-full tw-min-w-0 tw-flex-1" pt={{ dropdownButton: { className: 'tw-static tw-inline-flex tw-h-9 tw-w-9 tw-shrink-0 tw-items-center tw-justify-center tw-p-0' } }} value={date(day)} onChange={event => event.value && load(iso(event.value), team)} dateFormat="dd/mm/yy" showIcon /></label><label className="tw-grid tw-gap-1 tw-min-w-0 tw-max-w-full">Equipo<Dropdown appendTo={document.body} className="tw-flex tw-h-9 tw-w-full tw-min-w-0" value={team} options={teams.map(value => ({ label: value, value }))} onChange={event => load(day, event.value)} /></label><Tag value={`Revisión ${plan.revision || 0} · Publicada ${plan.published_revision || 'ninguna'}${dirty || requirementsDirty ? ' · Sin guardar' : ''}`} severity={dirty || requirementsDirty ? 'warning' : 'info'} /><Button className="tw-static tw-m-0 tw-h-auto tw-min-h-9 tw-max-w-full tw-whitespace-normal tw-shrink-0" label="Semana anterior" outlined size="small" onClick={() => moveWeek(-7)} /><Button className="tw-static tw-m-0 tw-h-auto tw-min-h-9 tw-max-w-full tw-whitespace-normal tw-shrink-0" label="Semana siguiente" outlined size="small" onClick={() => moveWeek(7)} /><Button className="tw-static tw-m-0 tw-h-auto tw-min-h-9 tw-max-w-full tw-whitespace-normal tw-shrink-0" label="Recargar" outlined size="small" onClick={() => load(day, team)} /><Button className="tw-static tw-m-0 tw-h-auto tw-min-h-9 tw-max-w-full tw-whitespace-normal tw-shrink-0" label="Guardar borrador" size="small" loading={operation === 'save'} disabled={busy && operation !== 'save'} onClick={() => send('save')} /><Button className="tw-static tw-m-0 tw-h-auto tw-min-h-9 tw-max-w-full tw-whitespace-normal tw-shrink-0" label="Sugerir descansos" outlined size="small" disabled={busy} onClick={() => send('optimize')} /><Button className="tw-static tw-m-0 tw-h-auto tw-min-h-9 tw-max-w-full tw-whitespace-normal tw-shrink-0" label="Publicar día" severity="success" size="small" disabled={busy} onClick={() => send('publish')} /><Button className="tw-static tw-m-0 tw-h-auto tw-min-h-9 tw-max-w-full tw-whitespace-normal tw-shrink-0" label="Publicar semana" severity="success" outlined size="small" loading={operation === 'publish-week'} disabled={busy && operation !== 'publish-week'} onClick={publishWeek} /></div><div className="tw-mt-3 tw-flex tw-flex-wrap tw-gap-1">{weekDays.map((value, index) => <Button className="tw-static tw-m-0 tw-h-auto tw-min-h-9 tw-max-w-full tw-whitespace-normal tw-shrink-0" key={value} label={weekdays[index] + ' ' + value.slice(8)} size="small" outlined={value !== day} onClick={() => load(value, team)} />)}</div>{(plan.warnings || []).map((warning, index) => <p key={index} className="tw-text-amber-700">{warning}</p>)}</Card>
<Card title="Semana publicada por persona" className="tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><div className="tw-flex tw-flex-wrap tw-items-end tw-gap-4"><Dropdown appendTo={document.body} className="tw-h-9" value={inspectPersonId} options={[{ label: 'Seleccionar integrante', value: '' }, ...(plan.people || []).map(person => ({ label: person.display_name, value: String(person.id) }))]} onChange={event => setInspectPersonId(event.value)} filter /><Button className="tw-h-9" label="Consultar semana" outlined size="small" onClick={inspectWeek} disabled={!inspectPersonId} /></div></Card>
    <Card title="Grilla de turnos" className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><WfmTimeline plan={plan} onMove={moveTimeline} onEdit={editShift} onMeeting={addMeeting} /></Card>
    <Card title="Turnos" className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><div className="tw-mb-3 tw-flex tw-flex-wrap tw-gap-2"><Dropdown appendTo={document.body} className="tw-h-9" value={personId} options={[{ label: 'Seleccionar integrante', value: '' }, ...(plan.people || []).filter(person => !plan.shifts.some(shift => shift.user_id === person.id)).map(person => ({ label: person.display_name, value: person.id }))]} onChange={event => setPersonId(event.value)} filter /><Button className="tw-h-9" label="Agregar turno" icon="pi pi-plus" size="small" onClick={() => { addPerson(personId); setPersonId(''); }} /></div><DataTable stripedRows value={plan.shifts || []} dataKey="user_id" size="small" scrollable emptyMessage="No hay turnos en el borrador"><Column header="Agente" body={shift => plan.people?.find(person => person.id === shift.user_id)?.display_name || shift.user_id} /><Column header="Bloques" body={shift => (shift.segments || []).map(segment => `${clock(segment.start)}–${clock(segment.end)}`).join(' · ')} /><Column header="Descanso" body={shift => clock(shift.break)} /><Column header="Extra" body={shift => `${(shift.overtime_slots || 0) / 2} h`} /><Column header="Excepciones" body={shift => (shift.exceptions || []).map(item => item.type).join(', ') || '—'} /><Column header="Acción" body={shift => <div className="tw-flex tw-gap-1"><Button className="tw-h-9" label="Editar" text size="small" onClick={() => editShift(shift)} /><Button className="tw-h-9" label="Quitar" text severity="danger" size="small" onClick={() => removePerson(shift.user_id)} /></div>} /></DataTable></Card>
<Card title="Demanda y cobertura" className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><DataTable stripedRows value={[{ label: 'Requeridos', value: slot => <InputNumber value={plan.demand[slot]} onValueChange={event => update({ ...plan, demand: plan.demand.map((value, index) => index === slot ? event.value : value) })} min={0} max={10000} useGrouping={false} inputStyle={{ width: 46 }} /> }, { label: 'Operativos', value: slot => coverage[slot]?.operational ?? '—' }, { label: 'Diferencia', value: slot => coverage[slot]?.difference ?? '—' }]} dataKey="label" size="small" scrollable scrollHeight="240px" className="tw-text-xs"><Column field="label" header="Franja" frozen />{Array.from({ length: Math.max(0, (plan.window?.[1] || 48) - (plan.window?.[0] || 0)) }, (_, index) => (plan.window?.[0] || 0) + index).map(slot => <Column key={slot} header={clock(slot)} body={row => row.value(slot)} style={{ minWidth: '76px' }} />)}</DataTable></Card>
    <Card title="Requerimientos semanales" className="tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><div className="tw-flex tw-flex-wrap tw-gap-3">{(plan.requirements || []).map((value, index) => <label key={index}>{weekdays[index]}<InputNumber className="tw-block" value={value} onValueChange={event => { coordinator.current.markEdited(); setRequirementsDirty(true); setPlan(currentPlan => ({ ...currentPlan, requirements: currentPlan.requirements.map((item, position) => position === index ? event.value : item) })); }} min={0} max={10000} useGrouping={false} /></label>)}</div><Button className="tw-mt-3 tw-h-9" label="Guardar requerimientos" size="small" loading={operation === 'requirements'} disabled={busy && operation !== 'requirements'} onClick={saveRequirements} /></Card>
    <Card title="Solicitudes" className="tw-min-w-0 tw-rounded-md tw-border tw-border-slate-200 tw-bg-white tw-shadow-sm"><div className="tw-mb-3 tw-flex tw-flex-wrap tw-items-end tw-gap-4"><label>Estado<Dropdown appendTo={document.body} className="tw-block tw-h-9" value={requestFilter} options={['PENDIENTE', 'APROBADA', 'RECHAZADA', 'CANCELADA', 'TODAS'].map(value => ({ label: value, value }))} onChange={event => setRequestFilter(event.value)} /></label><label>Tipo<Dropdown appendTo={document.body} className="tw-block tw-h-9" value={requestType} options={[{ label: 'Todos', value: '' }, { label: 'Ausencia', value: 'AUSENCIA' }, { label: 'Cambio de turno', value: 'CAMBIO_TURNO' }]} onChange={event => setRequestType(event.value)} /></label><label>Desde<Calendar appendTo={document.body} className="tw-inline-flex tw-h-9 tw-w-full tw-min-w-0" inputClassName="tw-w-full tw-min-w-0 tw-flex-1" pt={{ dropdownButton: { className: 'tw-static tw-inline-flex tw-h-9 tw-w-9 tw-shrink-0 tw-items-center tw-justify-center tw-p-0' } }} value={date(requestFrom)} onChange={event => setRequestFrom(iso(event.value))} dateFormat="dd/mm/yy" showIcon /></label><label>Hasta<Calendar appendTo={document.body} className="tw-inline-flex tw-h-9 tw-w-full tw-min-w-0" inputClassName="tw-w-full tw-min-w-0 tw-flex-1" pt={{ dropdownButton: { className: 'tw-static tw-inline-flex tw-h-9 tw-w-9 tw-shrink-0 tw-items-center tw-justify-center tw-p-0' } }} value={date(requestTo)} onChange={event => setRequestTo(iso(event.value))} dateFormat="dd/mm/yy" showIcon /></label><label>Persona<Dropdown appendTo={document.body} className="tw-block tw-h-9" value={requestPerson} options={[{ label: 'Todas', value: '' }, ...(plan.people || []).map(person => ({ label: person.display_name, value: String(person.id) }))]} onChange={event => setRequestPerson(event.value)} filter /></label><label>Persona o motivo<InputText className="tw-block tw-h-9" value={requestSearch} onChange={event => setRequestSearch(event.target.value)} /></label></div><DataTable stripedRows value={filteredRequests} dataKey="request_id" size="small" scrollable emptyMessage="No hay solicitudes"><Column header="Persona" body={item => item.display_name || item.requester_name || '—'} /><Column field="requested_date" header="Fecha" className="tw-whitespace-nowrap" /><Column field="request_type" header="Tipo" /><Column field="status" header="Estado" /><Column header="Detalle" className="operational-long-text" style={{ minWidth: '250px', whiteSpace: 'normal', wordWrap: 'break-word' }} body={item => item.reason || '—'} /><Column header="Acción" body={item => item.status === 'PENDIENTE' && <div className="tw-flex tw-gap-1"><Button className="tw-h-9" label="Aprobar" text size="small" onClick={() => setDecision({ ...item, decision: 'APROBAR' })} /><Button className="tw-h-9" label="Rechazar" text severity="danger" size="small" onClick={() => setDecision({ ...item, decision: 'RECHAZAR' })} /></div>} /></DataTable></Card><Dialog header={`${decision?.decision === 'APROBAR' ? 'Aprobar' : 'Rechazar'} solicitud`} visible={Boolean(decision)} onHide={() => setDecision(null)} modal appendTo={document.body} style={{ width: 'min(520px, 95vw)' }}><label className="tw-grid tw-gap-2">Nota de resolución<InputText className="tw-h-9" value={decisionNote} onChange={event => setDecisionNote(event.target.value)} maxLength={500} /></label><div className="tw-mt-3 tw-flex tw-justify-end tw-gap-2"><Button className="tw-h-9" label="Cancelar" text onClick={() => setDecision(null)} /><Button className="tw-h-9" label="Confirmar" loading={busy} onClick={decide} /></div></Dialog><Dialog header="Semana publicada" visible={Boolean(personWeek)} onHide={() => setPersonWeek(null)} modal appendTo={document.body} style={{ width: 'min(800px, 95vw)' }}>{personWeek && <div className="tw-grid tw-gap-2"><strong>{personWeek.person?.display_name}</strong>{(personWeek.days || []).map(item => <div key={item.date} className="tw-rounded-md tw-border tw-p-2"><strong>{item.date}</strong><div>{item.shift ? (item.shift.segments || []).map(segment => clock(segment.start) + '–' + clock(segment.end)).join(' · ') : item.published ? 'Libre publicado' : 'Sin publicación'}</div>{item.carry_in && <small>Continúa turno anterior hasta {clock(item.carry_in.end)}</small>}</div>)}</div>}</Dialog><Dialog header="Editar turno y excepciones" visible={Boolean(shiftEditor)} onHide={() => setShiftEditor(null)} modal appendTo={document.body} style={{ width: 'min(700px, 95vw)' }}>{shiftEditor && <div className="tw-grid tw-gap-3"><strong>{plan.people?.find(person => person.id === shiftEditor.user_id)?.display_name}</strong>{shiftEditor.segments.map((segment, index) => <div key={index} className="tw-flex tw-flex-wrap tw-items-end tw-gap-4"><label>Inicio<InputNumber className="tw-block" value={segment.start} onValueChange={event => editSegment(index, 'start', event.value)} min={0} max={47} useGrouping={false} /></label><label>Fin<InputNumber className="tw-block" value={segment.end} onValueChange={event => editSegment(index, 'end', event.value)} min={1} max={72} useGrouping={false} /></label><Button className="tw-h-9" label="Quitar bloque" text severity="danger" size="small" onClick={() => setShiftEditor(current => ({ ...current, segments: current.segments.filter((_, position) => position !== index) }))} /></div>)}<Button className="tw-h-9" label="Agregar bloque" outlined size="small" onClick={() => setShiftEditor(current => ({ ...current, segments: [...current.segments, { start: Math.min(47, current.segments.at(-1)?.end || 16), end: Math.min(72, (current.segments.at(-1)?.end || 16) + 2) }] }))} /><label>Descanso<InputNumber className="tw-block" value={shiftEditor.break} onValueChange={event => setShiftEditor(current => ({ ...current, break: event.value }))} min={0} max={71} useGrouping={false} /></label><label>Horas extra (franjas)<InputNumber className="tw-block" value={shiftEditor.overtime_slots || 0} onValueChange={event => setShiftEditor(current => ({ ...current, overtime_slots: event.value }))} min={0} max={24} useGrouping={false} /></label><label className="tw-flex tw-gap-2"><Checkbox checked={Boolean(shiftEditor.locked)} onChange={event => setShiftEditor(current => ({ ...current, locked: event.checked }))} />Bloquear descanso</label><strong>Excepciones</strong>{shiftEditor.exceptions.map((exception, index) => <div key={exception.id || index} className="tw-grid tw-gap-2 tw-rounded-md tw-border tw-p-2"><Dropdown appendTo={document.body} className="tw-h-9" value={exception.type} options={(plan.exception_types || ['Ausencia']).map(value => ({ label: value, value }))} onChange={event => editException(index, 'type', event.value)} /><div className="tw-flex tw-gap-2"><InputNumber value={exception.start} onValueChange={event => editException(index, 'start', event.value)} min={0} max={71} useGrouping={false} /><InputNumber value={exception.end} onValueChange={event => editException(index, 'end', event.value)} min={1} max={72} useGrouping={false} /></div><InputTextarea value={exception.note || ''} onChange={event => editException(index, 'note', event.target.value)} maxLength={240} /><Button className="tw-h-9" label="Quitar excepción" text severity="danger" size="small" onClick={() => setShiftEditor(current => ({ ...current, exceptions: current.exceptions.filter((_, position) => position !== index) }))} /></div>)}<Button className="tw-h-9" label="Agregar excepción" outlined size="small" onClick={() => setShiftEditor(current => ({ ...current, exceptions: [...current.exceptions, { id: `manual-${Date.now()}`, type: plan.exception_types?.[0] || 'Ausencia', start: current.segments[0]?.start || 0, end: current.segments[0]?.end || 1, note: '' }] }))} /><div className="tw-flex tw-justify-end tw-gap-2"><Button className="tw-h-9" label="Cancelar" text onClick={() => setShiftEditor(null)} /><Button className="tw-h-9" label="Aplicar al borrador" onClick={saveShiftEditor} /></div></div>}</Dialog>
    <Dialog header="Cambiar de planificación" visible={Boolean(navigationIntent)} onHide={() => setNavigationIntent(null)} modal appendTo={document.body} style={{ width: 'min(540px, 95vw)' }}>
      <p className="tw-whitespace-pre-line">{`${dirty || requirementsDirty ? 'Hay cambios sin guardar. Se descartarán al cambiar.\n' : ''}${coordinator.current.pendingMutation ? `La operación ${coordinator.current.pendingMutation.kind} sigue en curso para ${coordinator.current.pendingMutation.day} · ${coordinator.current.pendingMutation.team}. Su respuesta no reemplazará el nuevo plan.\n` : ''}¿Cambiar a ${navigationIntent?.day || ''} · ${navigationIntent?.team || ''}?`}</p>
      <div className="tw-mt-3 tw-flex tw-justify-end tw-gap-2"><Button className="tw-h-9" label="Permanecer" text onClick={() => setNavigationIntent(null)} /><Button className="tw-h-9" label="Cambiar planificación" severity="warning" onClick={() => navigationIntent && performLoad(navigationIntent.day, navigationIntent.team)} /></div>
    </Dialog>
    <Dialog header={confirmation?.title || 'Confirmar operación'} visible={Boolean(confirmation)} onHide={() => { const pending = confirmation; setConfirmation(null); pending?.cancel?.(); }} modal appendTo={document.body} style={{ width: 'min(620px, 95vw)' }}>
      <p className="tw-whitespace-pre-line tw-break-words">{confirmation?.message}</p>
      <div className="tw-mt-3 tw-flex tw-justify-end tw-gap-2"><Button className="tw-h-9" label="Cancelar" text onClick={() => { const pending = confirmation; setConfirmation(null); pending?.cancel?.(); }} /><Button className="tw-h-9" label={confirmation?.acceptLabel || 'Confirmar'} severity="success" onClick={() => { const pending = confirmation; setConfirmation(null); pending?.accept?.(); }} /></div>
    </Dialog>
  </div>;
}
