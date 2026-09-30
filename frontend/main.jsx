import React from 'react';
import { createRoot } from 'react-dom/client';
import { PrimeReactProvider } from 'primereact/api';
import 'primereact/resources/themes/lara-light-blue/theme.css';
import 'primereact/resources/primereact.min.css';
import 'primeicons/primeicons.css';
import './tailwind.css';
import { AppShell } from './app-shell.jsx';

const options = {
  ripple: true,
  inputStyle: 'outlined',
  appendTo: document.body,
  autoZIndex: true,
  pt: {
    card: {
      root: { className: 'tw-min-w-0 tw-max-w-full tw-rounded-md tw-border tw-border-[var(--border)] tw-bg-[var(--surface)] tw-text-[var(--text)] tw-shadow-sm' },
      body: { className: 'tw-p-3' },
      content: { className: 'tw-p-0' },
      title: { className: 'tw-mb-2 tw-text-sm tw-font-semibold' }
    },
    inputtext: { root: { className: 'tw-min-w-0 tw-max-w-full tw-px-2 tw-py-1.5 tw-text-[13px]' } },
    inputtextarea: { root: { className: 'tw-min-w-0 tw-max-w-full tw-p-2 tw-text-[13px]' } },
    dropdown: { root: { className: 'tw-min-w-0 tw-max-w-full tw-text-[13px]' }, input: { className: 'tw-px-2 tw-py-1.5 tw-text-[13px]' } },
    button: { root: { className: 'tw-min-h-9 tw-px-2 tw-py-1 tw-text-[13px]' } },
    dialog: { root: { className: 'tw-max-w-[calc(100vw-24px)] tw-text-[13px]' }, content: { className: 'tw-px-4 tw-py-3' } }
  }
};

createRoot(document.getElementById('root')).render(<PrimeReactProvider value={options}><AppShell /></PrimeReactProvider>);
