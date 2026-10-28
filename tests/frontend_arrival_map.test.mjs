import test from 'node:test';
import assert from 'node:assert/strict';
import { ALL_DEPARTMENT, arrivalDelayText, arrivalIndicationText, arrivalNeedsZone, arrivalReference, arrivalSituation, arrivalZoneDifferences, arrivalZones, departmentArrivalRows, arrivalIndicationCompact } from '../frontend/arrival-map-query.js';
import { displayLocation, displayService } from '../frontend/operational-labels.js';

test('las etiquetas operativas muestran prestaciones y ubicaciones legibles', () => {
  assert.equal(displayService('ML'), 'Mecánica Ligera');
  assert.equal(displayService('GRÚA'), 'Grúa');
  assert.equal(displayService('SINIESTROS'), 'Siniestros');
  assert.equal(displayLocation('MONTEVIDEO'), 'Montevideo');
  assert.equal(displayLocation('ciudad de la costa'), 'Ciudad de la Costa');
});

test('un clic obtiene ambas ciudades y el respaldo interior sin elegir zonas', () => {
  const items = [
    {id: 1, service:'ML', zone:'Colonia del Sacramento, Juan Lacaze', zone_members:['Colonia del Sacramento','Juan Lacaze'], indication_type:'MAXIMUM',minutes_max:60},
    {id: 2, service:'ML', zone:ALL_DEPARTMENT,indication_type:'TO_CONFIRM'},
  ];
  const rows = departmentArrivalRows({items, service:'ML'});
  assert.deepEqual(rows.map(row=>row.label), ['Colonia del Sacramento, Juan Lacaze','Resto del departamento']);
  assert.deepEqual(rows.map(row=>arrivalIndicationCompact(row.standard)), ['Máximo de 60 min','A confirmar']);
  assert.equal(departmentArrivalRows({items,service:'SINIESTROS'})[0].situation.state,'missing');
});

test('demora local sustituye solo la localidad afectada y la prestación correspondiente', () => {
  const items = [{id:1,service:'ML',zone:'Pocitos, Buceo',zone_members:['Pocitos','Buceo'],indication_type:'MAXIMUM',minutes_max:30}];
  const delays = [{id:3,service:'ML',zone:'Pocitos',message:'Máximo de',minutes:60}];
  const rows = departmentArrivalRows({items,delays,service:'ML'});
  assert.deepEqual(rows.slice(0,2).map(row=>[row.label,row.situation.state]),[['Pocitos','exception'],['Buceo','habitual']]);
  assert.equal(rows[0].situation.answer,'Máximo de 60 minutos');
  assert.equal(departmentArrivalRows({items,delays,service:'GRÚA'})[0].situation.state,'missing');
  assert.equal(departmentArrivalRows({items,delays:[{...delays[0],service:'TODAS'}],service:'GRÚA'})[0].situation.state,'exception');
  assert.equal(departmentArrivalRows({items,delays:[{...delays[0],needs_review:true}],service:'ML'})[0].situation.state,'review');
  assert.equal(departmentArrivalRows({items,delays,service:'ML',mapStatus:'error'})[0].situation.state,'unverified');
});

const standards = [
  { id: 1, service: 'ML', zone: ALL_DEPARTMENT, base_estimated_minutes: 60 },
  { id: 2, service: 'ML', zone: 'Pocitos', base_estimated_minutes: 40 },
  { id: 3, service: 'GRÚA', zone: ALL_DEPARTMENT, base_estimated_minutes: 75 },
];
const delay = { id: 4, service: 'ML', zone: 'Pocitos', message: 'A confirmar', needs_review: false };

test('un departamento sin demoras ofrece varias prestaciones y conserva la resolución de zona', () => {
  assert.equal(arrivalReference(standards, 'ML', 'Pocitos').base_estimated_minutes, 40);
  assert.equal(arrivalReference(standards, 'ML', 'Buceo').base_estimated_minutes, 60);
  assert.equal(arrivalReference(standards, 'GRÚA', 'Pocitos').base_estimated_minutes, 75);
  assert.deepEqual(arrivalZoneDifferences(standards, 'ML').map(item => item.zone), ['Pocitos']);
  assert.equal(arrivalNeedsZone({delays:[],items:standards,service:'ML',zone:ALL_DEPARTMENT,standard:standards[0]}),true);
  assert.equal(arrivalNeedsZone({delays:[],items:standards,service:'GRÚA',zone:ALL_DEPARTMENT,standard:standards[2]}),false);
  assert.equal(arrivalSituation({ delays: [], service: 'ML', zone: 'Buceo', mapStatus: 'ready', standardStatus: 'ready', standard: standards[0] }).state, 'habitual');
});

test('una excepción prevalece sobre el estándar de la misma prestación y zona', () => {
  const result = arrivalSituation({ delays: [delay], service: 'ML', zone: 'Pocitos', mapStatus: 'ready', standardStatus: 'ready', standard: standards[1] });
  assert.equal(result.state, 'exception');
  assert.equal(result.label, 'Afectación vigente');
  assert.equal(result.answer, 'A confirmar');
  assert.deepEqual(result.matching.map(item => item.id), [4]);
  assert.equal(arrivalReference(standards, 'ML', 'Pocitos').base_estimated_minutes, 40);
  assert.equal(arrivalSituation({ delays: [delay], service: 'GRÚA', zone: 'Pocitos', mapStatus: 'ready', standardStatus: 'ready', standard: standards[2] }).state, 'habitual');
  assert.equal(arrivalSituation({ delays: [{ ...delay, service: 'TODAS' }], service: 'GRÚA', zone: 'Pocitos', mapStatus: 'ready', standardStatus: 'ready', standard: standards[2] }).state, 'exception');
  assert.equal(arrivalSituation({ delays: [delay], service: 'ML', zone: ALL_DEPARTMENT, mapStatus: 'ready', standardStatus: 'ready', standard: standards[0] }).state, 'select_zone');
  assert.equal(arrivalSituation({delays:[],items:standards,service:'ML',zone:ALL_DEPARTMENT,mapStatus:'ready',standardStatus:'ready',standard:standards[0]}).state,'select_zone');
  assert.equal(arrivalSituation({delays:[{...delay,service:'TODAS',zone:ALL_DEPARTMENT}],items:standards,service:'GRÚA',zone:ALL_DEPARTMENT,mapStatus:'ready',standardStatus:'ready',standard:standards[2]}).answer,'A confirmar');
});

test('una revisión vencida, solapamiento o fuente fallida impide confirmar el habitual', () => {
  const input = { delays: [{ ...delay, needs_review: true }], service: 'ML', zone: 'Pocitos', mapStatus: 'ready', standardStatus: 'ready', standard: standards[1] };
  assert.equal(arrivalSituation(input).state, 'review');
  assert.equal(arrivalSituation(input).answer, 'A confirmar con Planificación');
  assert.equal(arrivalSituation({ ...input, delays: [delay, { ...delay, id: 5 }] }).state, 'overlap');
  assert.equal(arrivalSituation({ ...input, delays: [delay, { ...delay, id: 5 }] }).answer, 'A confirmar con Planificación');
  assert.equal(arrivalSituation({ ...input, mapStatus: 'error' }).state, 'unverified');
  assert.equal(arrivalSituation({ ...input, mapStatus: 'error' }).answer, 'Información no disponible');
  assert.equal(arrivalSituation({ ...input, delays: [], standardStatus: 'error' }).state, 'unverified');
  assert.equal(arrivalSituation({ ...input, delays: [], standardStatus: 'idle' }).state, 'unverified');
  assert.equal(arrivalSituation({ ...input, delays: [], items: standards, zone: ALL_DEPARTMENT, standardStatus: 'error' }).state, 'unverified');
});

test('al normalizar desaparece la excepción y las zonas libres no se pierden', () => {
  assert.equal(arrivalSituation({ delays: [], service: 'ML', zone: 'Pocitos', mapStatus: 'ready', standardStatus: 'ready', standard: standards[1] }).state, 'habitual');
  assert.equal(arrivalSituation({ delays: [], service: 'ML', zone: 'Pocitos', mapStatus: 'ready', standardStatus: 'ready', standard: standards[1] }).answer, '40 minutos habituales');
  assert.deepEqual(arrivalZones([ALL_DEPARTMENT, 'Pocitos'], [{ zone: 'Buceo, Paso Carrasco' }]), [ALL_DEPARTMENT, 'Pocitos', 'Buceo', 'Paso Carrasco']);
});

test('máximos, intervalos y A confirmar conservan el texto y el ámbito agrupado', () => {
  const values = [
    { id: 11, service: 'ML', zone: 'Pocitos, Buceo', zone_members: ['Pocitos', 'Buceo'], indication_type: 'MAXIMUM', minutes_max: 30 },
    { id: 12, service: 'SINIESTROS', zone: 'Pocitos', indication_type: 'INTERVAL', minutes_min: 30, minutes_max: 45 },
    { id: 13, service: 'GRÚA', zone: ALL_DEPARTMENT, indication_type: 'TO_CONFIRM' },
  ];
  assert.equal(arrivalIndicationText(arrivalReference(values, 'ML', 'Buceo')), 'Máximo de 30 minutos');
  assert.equal(arrivalIndicationText(arrivalReference(values, 'SINIESTROS', 'Pocitos')), 'Entre 30 y 45 minutos');
  assert.equal(arrivalIndicationText(arrivalReference(values, 'GRÚA', 'Buceo')), 'A confirmar');
  assert.equal(arrivalReference(values, 'SINIESTROS', 'Buceo'), null);
  assert.deepEqual(arrivalZones([ALL_DEPARTMENT], values), [ALL_DEPARTMENT, 'Pocitos', 'Buceo']);
  const unconfirmed = arrivalSituation({ delays: [], service: 'GRÚA', zone: 'Buceo', mapStatus: 'ready', standardStatus: 'ready', standard: values[2] });
  assert.equal(unconfirmed.state, 'unconfirmed');
  assert.match(unconfirmed.message, /No comuniques un tiempo numérico/);
});

test('las indicaciones de demora no se suman ni se reinterpretan', () => {
  assert.equal(arrivalDelayText({message:'Máximo de',minutes:30}), 'Máximo de 30 minutos');
  assert.equal(arrivalDelayText({message:'Intervalo estimado',minutes_min:60,minutes_max:90}), 'Entre 60 y 90 minutos');
  assert.match(arrivalDelayText({message:'Margen de',minutes:25}), /confirmar tiempo total/);
  assert.equal(arrivalDelayText({message:'No confirmar tiempos'}), 'No confirmar tiempos');
  assert.equal(arrivalDelayText({message:'No generar servicio'}), 'No generar servicio');
});
