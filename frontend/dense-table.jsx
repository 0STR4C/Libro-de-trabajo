import React from 'react';
import { DataTable as PrimeDataTable } from 'primereact/datatable';

export function DataTable({ className = '', ...props }) {
  return <PrimeDataTable {...props} size="small" stripedRows className={[
    'dense-data-table tw-min-w-0 tw-max-w-full tw-text-[13px]',
    '[&_.p-datatable-wrapper]:tw-max-w-full [&_.p-datatable-wrapper]:tw-overflow-x-auto',
    '[&_th]:tw-h-8 [&_th]:tw-px-2 [&_th]:tw-py-1 [&_th]:tw-text-xs [&_th]:tw-font-medium',
    '[&_td]:tw-h-9 [&_td]:tw-px-2 [&_td]:tw-py-1 [&_td]:tw-text-[13px] [&_td]:tw-leading-tight',
    '[&_td:not(.tw-whitespace-nowrap)]:tw-whitespace-normal [&_td]:tw-break-words',
    '[&_.p-datatable-tbody>tr:nth-child(even):not(.notice-unassigned):not(.notice-own):not(.notice-waiting):not(.delay-review-row):not(.active-delay)>td]:tw-bg-[var(--surface-subtle)]',
    '[&_.p-datatable-tbody>tr.delay-review-row>td]:tw-bg-[var(--color-urgente-bg)]',
    '[&_.p-datatable-tbody>tr.active-delay>td]:tw-bg-[var(--color-primary-bg)]',
    '[&_.p-datatable-tbody>tr:hover>td]:tw-bg-[var(--surface-muted)]',
    className
  ].join(' ')} />;
}
