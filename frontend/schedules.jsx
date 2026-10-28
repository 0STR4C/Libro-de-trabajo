import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Calendar } from 'primereact/calendar';
import { Card } from 'primereact/card';
import { Column } from 'primereact/column';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { ProgressSpinner } from 'primereact/progressspinner';
import { SelectButton } from 'primereact/selectbutton';
import { DataTable } from './dense-table.jsx';
import { createScheduleResponseGate, indexSchedules, shiftScheduleDay } from './schedule-grid.js';

const weekdays = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
const dayColors = [
  'tw-bg-sky-50 dark:tw-bg-sky-950/40',
  'tw-bg-indigo-50 dark:tw-bg-indigo-950/40',
  'tw-bg-violet-50 dark:tw-bg-violet-950/40',
  'tw-bg-cyan-50 dark:tw-bg-cyan-950/40',
  'tw-bg-blue-50 dark:tw-bg-blue-950/40',
  'tw-bg-slate-100 dark:tw-bg-slate-800',
  'tw-bg-zinc-100 dark:tw-bg-zinc-800',
];
const iso = value => value ? `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}` : '';
const date = value => value ? new Date(`${value}T12:00:00`) : null;
const monday = value => shiftScheduleDay(value, -((date(value).getDay() + 6) % 7));
const clock = slot => slot == null ? '—' : `${String(Math.floor(Number(slot) / 2) % 24).padStart(2, '0')}:${Number(slot) % 2 ? '30' : '00'}${Number(slot) >= 48 ? ' +1' : ''}`;
const minutesText = minutes => `${Math.floor(minutes / 60)} h${minutes % 60 ? ` ${minutes % 60} min` : ''}`;

function plannedMinutes(row, continuation = false) {
  if (row.published_day) return 0;
  const floor = continuation ? 48 : 0;
  const ceiling = continuation ? 96 : 72;
  const segments = row.segments?.length ? row.segments : row.start_slot != null && row.end_slot != null ? [{ start: row.start_slot, end: row.end_slot }] : [];
  let slots = 0;
  for (const segment of segments) {
    const start = Math.max(floor, Number(segment.start));
    const end = Math.min(ceiling, Number(segment.end));
    if (end <= start) continue;
    slots += end - start;
    if (row.break_slot != null) {
      const breakStart = Number(row.break_slot);
      const breakEnd = breakStart + Number(row.break_duration || 1);
      slots -= Math.max(0, Math.min(end, breakEnd) - Math.max(start, breakStart));
    }
  }
  return Math.max(0, slots * 30);
}

function ShiftDetail({ entry, compact = false }) {
  const { row, continuation } = entry;
  if (row.published_day) return <span className="tw-text-app-muted">Libre publicado</span>;
  if (continuation) {
    const breakStart = Number(row.break_slot);
    const breakEnd = breakStart + Number(row.break_duration || 1);
    return <div className="tw-grid tw-gap-1 tw-rounded tw-border tw-border-app-border tw-p-2">
      <span className="tw-font-medium">Continúa del día anterior</span>
      <span>Salida {clock(Number(row.end_slot) - 48)}</span>
      {row.break_slot != null && breakEnd > 48 && <span className="tw-text-app-muted">Descanso {clock(Math.max(48, breakStart) - 48)}–{clock(breakEnd - 48)}</span>}
      {!compact && <span className="tw-text-app-muted">Tramo {minutesText(plannedMinutes(row, true))}</span>}
    </div>;
  }
  const segments = row.segments?.length ? row.segments : row.start_slot != null && row.end_slot != null ? [{ start: row.start_slot, end: row.end_slot }] : [];
  return <div className="tw-grid tw-gap-1 tw-rounded tw-border tw-border-app-border tw-p-2">
    {segments.map((segment, index) => <div key={index} className="tw-grid tw-gap-0.5">
      <><strong className="tw-font-semibold">Entrada {clock(segment.start)}</strong><span>Salida {clock(segment.end)}</span></>
    </div>)}
    {row.break_slot != null && <span className="tw-text-app-muted">Descanso {clock(row.break_slot)}–{clock(Number(row.break_slot) + Number(row.break_duration || 1))}</span>}
    {Number(row.overtime_slots) > 0 && <span className="tw-text-app-muted">Extras {minutesText(Number(row.overtime_slots) * 30)}</span>}
    {!compact && <span className="tw-text-app-muted">Duración {minutesText(plannedMinutes(row))}</span>}
  </div>;
}

function DayEntries({ entries, compact = false }) {
  if (!entries.length) return <span className="tw-text-app-muted">Sin publicación</span>;
  return <div className="tw-grid tw-gap-1">{entries.map((entry, index) => <ShiftDetail key={`${entry.row.id}:${entry.continuation}:${index}`} entry={entry} compact={compact} />)}</div>;
}

export function SchedulesView({ model }) {
  const [view, setView] = useState(model.filters.view === 'mine' ? 'mine' : 'team');
  const [week, setWeek] = useState(model.filters.week);
  const [snapshot, setSnapshot] = useState(model.snapshot);
  const [search, setSearch] = useState('');
  const [role, setRole] = useState('');
  const [focusDay, setFocusDay] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const gate = useRef(createScheduleResponseGate(model.filters.week));
  const localRequest = useRef(false);

  const loadWeek = async value => {
    const next = monday(value);
    const ticket = gate.current.begin(next);
    localRequest.current = true;
    setWeek(next); setFocusDay(''); setLoading(true); setError(''); setSnapshot(null);
    model.onStateChange?.({ week: next, view });
    try {
      const result = await model.request(`/api/schedules/team?week=${encodeURIComponent(next)}`);
      if (gate.current.accepts(ticket)) setSnapshot(result);
    } catch (failure) {
      if (gate.current.accepts(ticket)) setError(failure.message);
    } finally {
      if (gate.current.accepts(ticket)) { localRequest.current = false; setLoading(false); }
    }
  };
  useEffect(() => {
    if (localRequest.current || !gate.current.matches(model.filters.week)) return;
    setWeek(model.filters.week); setSnapshot(model.snapshot); setError('');
  }, [model.snapshot, model.filters.week]);
  useEffect(() => { setView(model.filters.view === 'mine' ? 'mine' : 'team'); }, [model.filters.view]);
  useEffect(() => () => gate.current.invalidate(), []);

  const selectView = value => { if (!value) return; setView(value); setFocusDay(''); model.onStateChange?.({ week, view: value }); };
  const today = iso(new Date());
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => shiftScheduleDay(week, index)), [week]);
  const index = useMemo(() => indexSchedules(snapshot?.rows || []), [snapshot]);
  const people = snapshot?.people || [];
  const filteredPeople = useMemo(() => people.filter(person =>
    (!role || person.role_name === role) &&
    (!search.trim() || person.display_name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
  ), [people, role, search]);
  const roles = useMemo(() => [...new Set(people.map(person => person.role_name).filter(Boolean))], [people]);
  const displayedDays = focusDay && days.includes(focusDay) ? [focusDay] : days;
  const ownDays = days.map((day, position) => ({ day, position, entries: index.byPersonDay.get(`${model.userId}:${day}`) || [] }));
  const ownMinutes = ownDays.reduce((sum, item) => sum + item.entries.reduce((total, entry) => total + (entry.continuation && days.includes(entry.row.schedule_date) ? 0 : plannedMinutes(entry.row, entry.continuation)), 0), 0);

  return <div className="tw-grid tw-min-w-0 tw-gap-3 tw-text-[13px]">
    <Card className="tw-rounded-md tw-border tw-border-app-border tw-bg-app-surface tw-shadow-sm">
      <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-3">
        <SelectButton aria-label="Vista de horarios" value={view} options={[{ label: 'Equipo', value: 'team' }, { label: 'Mis horarios', value: 'mine' }]} onChange={event => selectView(event.value)} />
        {model.canRequest && <Button label="Mis solicitudes" icon="pi pi-inbox" text size="small" onClick={model.onOpenRequests} />}
      </div>
      <div className="tw-mt-3 tw-flex tw-flex-wrap tw-items-end tw-gap-3">
        <Button icon="pi pi-chevron-left" outlined size="small" aria-label="Semana anterior" onClick={() => loadWeek(shiftScheduleDay(week, -7))} />
        <label className="tw-grid tw-gap-1">Semana de<Calendar appendTo={document.body} value={date(week)} onChange={event => event.value && loadWeek(iso(event.value))} dateFormat="dd/mm/yy" showIcon /></label>
        <Button icon="pi pi-chevron-right" outlined size="small" aria-label="Semana siguiente" onClick={() => loadWeek(shiftScheduleDay(week, 7))} />
        <Button label="Hoy" icon="pi pi-calendar" outlined size="small" onClick={() => { if (monday(today) !== week) loadWeek(today); setFocusDay(today); }} />
        {focusDay && <Button label="Semana completa" text size="small" onClick={() => setFocusDay('')} />}
        <span className="tw-self-center tw-font-semibold tw-text-app-text">{days[0].slice(8)}/{days[0].slice(5, 7)} – {days[6].slice(8)}/{days[6].slice(5, 7)}/{days[6].slice(0, 4)}</span>
      </div>
    </Card>

    {view === 'team' && <Card className="tw-rounded-md tw-border tw-border-app-border tw-bg-app-surface tw-shadow-sm">
      <div className="tw-flex tw-flex-wrap tw-items-end tw-gap-3">
        <label className="tw-grid tw-min-w-[230px] tw-flex-1 tw-gap-1">Buscar compañero<InputText value={search} onChange={event => setSearch(event.target.value)} placeholder="Nombre" /></label>
        <label className="tw-grid tw-min-w-[180px] tw-gap-1">Rol<Dropdown appendTo={document.body} value={role} options={[{ label: 'Todos', value: '' }, ...roles.map(value => ({ label: value, value }))]} onChange={event => setRole(event.value)} /></label>
        <span className="tw-self-center tw-text-app-muted">{filteredPeople.length} personas</span>
      </div>
    </Card>}

    {loading && <div role="status" className="tw-flex tw-items-center tw-gap-3 tw-p-4"><ProgressSpinner style={{ width: 26, height: 26 }} strokeWidth="5" />Cargando horarios…</div>}
    {error && <Card className="tw-border tw-border-red-200 tw-bg-app-surface"><div role="alert" className="tw-flex tw-flex-wrap tw-items-center tw-gap-3"><strong>Error de carga</strong><span>{error}</span><Button label="Reintentar" size="small" onClick={() => loadWeek(week)} /></div></Card>}

    {!loading && !error && snapshot && view === 'team' && <Card className="tw-min-w-0 tw-rounded-md tw-border tw-border-app-border tw-bg-app-surface tw-shadow-sm" pt={{ body: { className: 'tw-p-0' }, content: { className: 'tw-p-0' } }}>
      <DataTable value={filteredPeople} dataKey="id" paginator rows={50} scrollable scrollHeight="min(65vh, 660px)" emptyMessage="No hay personas para la búsqueda" rowClassName={person => Number(person.id) === Number(model.userId) ? '[&>td]:tw-bg-blue-50/70 dark:[&>td]:tw-bg-blue-950/30' : ''} className="tw-min-w-0 [&_.p-datatable-thead>tr>th]:tw-sticky [&_.p-datatable-thead>tr>th]:tw-top-0 [&_.p-datatable-thead>tr>th]:tw-z-20">
        <Column frozen alignFrozen="left" header="Persona" style={{ minWidth: '190px', width: '190px' }} body={person => <div className="tw-grid tw-gap-0.5"><strong className="tw-font-semibold">{person.display_name}</strong><small className="tw-text-app-muted">{person.role_name}{Number(person.id) === Number(model.userId) ? ' · Vos' : ''}</small></div>} />
        {displayedDays.map(day => { const dayIndex = days.indexOf(day); return <Column key={day} headerClassName={dayColors[dayIndex]} header={<div className={`tw-grid tw-gap-0.5 tw-rounded tw-p-1 ${dayColors[dayIndex]} ${day === today ? 'tw-ring-1 tw-ring-blue-300' : ''}`}><strong>{weekdays[dayIndex]}</strong><span>{day.slice(8)}/{day.slice(5, 7)}</span></div>} style={{ minWidth: '158px', width: '158px', verticalAlign: 'top' }} body={person => <DayEntries compact entries={index.byPersonDay.get(`${person.id}:${day}`) || []} />} />; })}
      </DataTable>
    </Card>}

    {!loading && !error && snapshot && view === 'mine' && <>
      <Card className="tw-rounded-md tw-border tw-border-app-border tw-bg-app-surface tw-shadow-sm"><div className="tw-flex tw-flex-wrap tw-items-center tw-gap-3"><strong>Mi semana</strong><span className="tw-text-app-muted">{minutesText(ownMinutes)} planificadas</span></div></Card>
      <div className="tw-grid tw-min-w-0 tw-gap-3 lg:tw-grid-cols-2 2xl:tw-grid-cols-3">
        {ownDays.filter(item => !focusDay || item.day === focusDay).map(({ day, position, entries }) => <Card key={day} className={`tw-min-w-0 tw-rounded-md tw-border tw-border-app-border tw-bg-app-surface tw-shadow-sm ${day === today ? 'tw-ring-1 tw-ring-blue-300' : ''}`}>
          <div className={`tw-mb-3 tw-flex tw-items-center tw-justify-between tw-rounded tw-p-2 ${dayColors[position]}`}><strong>{weekdays[position]}</strong><span>{day.slice(8)}/{day.slice(5, 7)}</span></div>
          <DayEntries entries={entries} />
        </Card>)}
      </div>
    </>}
  </div>;
}
