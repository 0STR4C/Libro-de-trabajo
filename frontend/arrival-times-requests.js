// Una sola puerta para aceptar páginas, incluidas las recuperaciones tras conflictos.
export function createArrivalPageRequests() {
  let sequence = 0;
  return {
    invalidate() { sequence += 1; },
    async load(fetchPage, { isActive, accept, reject, finish }) {
      const ticket = ++sequence;
      if (!isActive()) return false;
      try {
        const page = await fetchPage();
        if (ticket !== sequence || !isActive()) return false;
        accept(page);
        return true;
      } catch (error) {
        if (ticket === sequence && isActive() && !error.stale) reject(error);
        return false;
      } finally {
        if (ticket === sequence) finish();
      }
    }
  };
}
