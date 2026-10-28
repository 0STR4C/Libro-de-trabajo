// Coordina escrituras de cotizaciones dentro de una sesión de pantalla.
// Un resultado sólo pertenece a la revisión que inició su solicitud.
export function createQuoteRequestGuard() {
  let revision = 0;
  let pending = false;
  let submitted = null;
  return {
    get pending() { return pending; },
    get submitted() { return submitted; },
    invalidate() { revision += 1; },
    begin(fingerprint) {
      if (pending) return { reason: 'pending' };
      if (submitted === fingerprint) return { reason: 'duplicate' };
      pending = true;
      submitted = fingerprint;
      revision += 1;
      return { revision };
    },
    isCurrent(token) { return token === revision; },
    finish() { pending = false; },
    rejectKnown() { submitted = null; },
    allowNew() { submitted = null; revision += 1; },
  };
}
