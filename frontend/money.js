const numberUY = new Intl.NumberFormat('es-UY', {
  useGrouping: true,
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});
const numberUYWithCents = new Intl.NumberFormat('es-UY', {
  useGrouping: true,
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatUYU(value, { cents = false } = {}) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return '—';
  return `$ ${(cents || !Number.isInteger(amount) ? numberUYWithCents : numberUY).format(amount)}`;
}

export const uyuInputProps = { locale: 'es-UY', prefix: '$ ', useGrouping: true, minFractionDigits: 0, maxFractionDigits: 2 };
