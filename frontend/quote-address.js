const coordinatePattern = /^\s*-?\d{1,2}(?:\.\d+)?\s*[,; ]\s*-?\d{1,3}(?:\.\d+)?\s*$/;
const googleDomains = ['google.com', 'google.com.uy', 'google.com.ar', 'google.com.br'];

function isGoogleMapLink(text) {
  try {
    const url = new URL(text);
    const host = url.hostname.toLowerCase();
    return ['http:', 'https:'].includes(url.protocol) && (
      host === 'goo.gl' || host === 'maps.app.goo.gl' ||
      googleDomains.some(domain => host === domain || host.endsWith(`.${domain}`))
    );
  } catch { return false; }
}

export function isDirectLocation(value) {
  const text = String(value || '').trim();
  return coordinatePattern.test(text) || isGoogleMapLink(text);
}

export function selectedCoordinates(item) {
  return `${Number(item.latitude).toFixed(6)}, ${Number(item.longitude).toFixed(6)}`;
}

export function manualRegionPoints(form) {
  return [form.origin, form.destination, form.include_mobile ? form.mobile_origin : null]
    .filter(isDirectLocation);
}

export function regionalSelection(form) {
  return ['origin', 'destination', ...(form.include_mobile ? ['mobile_origin'] : [])]
    .some(field => form[field] && form[`${field}_confirmed`] && form[`${field}_country`] && form[`${field}_country`] !== 'UY');
}
