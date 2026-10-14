export const REQUEST_TIMEOUT_MS = 30_000;

export function requestDeadline(controller, milliseconds = REQUEST_TIMEOUT_MS) {
  let expired = false;
  const timer = setTimeout(() => {
    expired = true;
    controller.abort();
  }, milliseconds);
  return { expired: () => expired, clear: () => clearTimeout(timer) };
}

export function requestTimeoutError(changesData) {
  const error = new Error(changesData
    ? 'Pasaron 30 segundos sin respuesta. No se pudo confirmar si el cambio se guardó. Consultá el estado actual antes de volver a intentarlo.'
    : 'La consulta tardó más de 30 segundos. Reintentá la carga.');
  error.timedOut = true;
  error.uncertain = changesData;
  return error;
}
