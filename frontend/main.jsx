import React from 'react';
import { flushSync } from 'react-dom';
import { createRoot } from 'react-dom/client';
import { PrimeReactProvider } from 'primereact/api';
import { Button } from 'primereact/button';
import { Card } from 'primereact/card';
import { Calendar } from 'primereact/calendar';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { Menu } from 'primereact/menu';
import { SelectButton } from 'primereact/selectbutton';
import { Tag } from 'primereact/tag';

import 'primereact/resources/themes/lara-light-blue/theme.css';
import 'primereact/resources/primereact.min.css';
import 'primeicons/primeicons.css';
import './tailwind.css';
import { DelaysView, NoticesView } from './operations.jsx';
import { DashboardView } from './dashboard.jsx';
import { QuoteView } from './quotes.jsx';
import { TransfersView } from './transfers.jsx';
import { SchedulesView } from './schedules.jsx';
import { StandardsView } from './standards.jsx';
import { SettingsView } from './settings.jsx';
import { AuditView } from './audit.jsx';
import { WfmView } from './wfm.jsx';
import { LoginView } from './login.jsx';
export { DashboardView, QuoteView, TransfersView };
export { DelaysView, NoticesView };

const defaultPrimeReactOptions = { ripple: true, inputStyle: 'outlined' };
let dashboardRoot = null;
let noticesRoot = null;
let quotesRoot = null;
let delaysRoot = null;
let transfersRoot = null;
let schedulesRoot = null;
let standardsRoot = null;
let settingsRoot = null;
let auditRoot = null;
let wfmRoot = null;
let loginRoot = null;

export function mountDashboard(element, model) {
  if (!element) throw new TypeError('mountDashboard requiere el contenedor de Resumen');
  dashboardRoot?.unmount();
  dashboardRoot = createRoot(element);
  flushSync(() => {
    dashboardRoot.render(
      <PrimeReactProvider value={defaultPrimeReactOptions}>
        <DashboardView model={model} />
      </PrimeReactProvider>
    );
  });
}

export function unmountDashboard() {
  dashboardRoot?.unmount();
  dashboardRoot = null;
}

export function mountNotices(element, model) {
  if (!element) throw new TypeError('mountNotices requiere el contenedor de Avisos');
  noticesRoot?.unmount();
  noticesRoot = createRoot(element);
  flushSync(() => {
    noticesRoot.render(
      <PrimeReactProvider value={defaultPrimeReactOptions}>
        <NoticesView model={model} />
      </PrimeReactProvider>
    );
  });
}

export function unmountNotices() {
  noticesRoot?.unmount();
  noticesRoot = null;
}

function mountWithPrimeReact(root, element, view) {
  root?.unmount();
  const nextRoot = createRoot(element);
  flushSync(() => {
    nextRoot.render(<PrimeReactProvider value={defaultPrimeReactOptions}>{view}</PrimeReactProvider>);
  });
  return nextRoot;
}

export function mountQuotes(element, model) {
  if (!element) throw new TypeError('mountQuotes requiere el contenedor del Cotizador');
  quotesRoot = mountWithPrimeReact(quotesRoot, element, <QuoteView model={model} />);
}

export function unmountQuotes() {
  quotesRoot?.unmount();
  quotesRoot = null;
}

export function mountDelays(element, model) {
  if (!element) throw new TypeError('mountDelays requiere el contenedor de Demoras');
  delaysRoot = mountWithPrimeReact(delaysRoot, element, <DelaysView model={model} />);
}

export function unmountDelays() {
  delaysRoot?.unmount();
  delaysRoot = null;
}

export function mountTransfers(element, model) {
  if (!element) throw new TypeError('mountTransfers requiere el contenedor de Programados');
  transfersRoot = mountWithPrimeReact(transfersRoot, element, <TransfersView model={model} />);
}

export function unmountTransfers() {
  transfersRoot?.unmount();
  transfersRoot = null;
}

export function mountSchedules(element, model) { schedulesRoot = mountWithPrimeReact(schedulesRoot, element, <SchedulesView model={model} />); }
export function unmountSchedules() { schedulesRoot?.unmount(); schedulesRoot = null; }
export function mountStandards(element, model) { standardsRoot = mountWithPrimeReact(standardsRoot, element, <StandardsView model={model} />); }
export function unmountStandards() { standardsRoot?.unmount(); standardsRoot = null; }
export function mountSettings(element, model) { settingsRoot = mountWithPrimeReact(settingsRoot, element, <SettingsView model={model} />); }
export function unmountSettings() { settingsRoot?.unmount(); settingsRoot = null; }
export function mountAudit(element, model) { auditRoot = mountWithPrimeReact(auditRoot, element, <AuditView model={model} />); }
export function unmountAudit() { auditRoot?.unmount(); auditRoot = null; }
export function mountWfm(element, model) { wfmRoot = mountWithPrimeReact(wfmRoot, element, <WfmView model={model} />); }
export function unmountWfm() { wfmRoot?.unmount(); wfmRoot = null; }
export function mountLogin(element, model) { loginRoot = mountWithPrimeReact(loginRoot, element, <LoginView model={model} />); }
export function unmountLogin() { loginRoot?.unmount(); loginRoot = null; }

const mountContract = {
  mountDashboard,
  unmountDashboard,
  mountNotices,
  unmountNotices,
  mountQuotes,
  unmountQuotes,
  mountDelays,
  unmountDelays,
  mountTransfers,
  unmountTransfers,
  mountSchedules,
  unmountSchedules,
  mountStandards,
  unmountStandards,
  mountSettings,
  unmountSettings,
  mountAudit,
  unmountAudit,
  mountWfm,
  unmountWfm,
  mountLogin,
  unmountLogin
};
window.LibroTrabajoUI = mountContract;
window.ReactApp = mountContract;

export { Button, Calendar, Card, Column, DataTable, Dropdown, InputText, React, PrimeReactProvider, SelectButton, Tag };
