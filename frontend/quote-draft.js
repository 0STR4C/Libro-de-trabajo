import { isDirectLocation } from './quote-address.js';

export const blank = { task_number: '', coverage: 'insured', special: false, gavilan: false, origin: '', destination: '', mobile_origin: '', origin_country: 'UY', destination_country: 'UY', mobile_origin_country: 'UY', origin_entry_mode: 'address', destination_entry_mode: 'address', mobile_origin_entry_mode: 'address', origin_confirmed: false, destination_confirmed: false, mobile_origin_confirmed: false, manual_trip_km: null, manual_mobile_km: null, manual_toll_count: null, include_mobile: false, include_tolls: false };

export function normalizeQuoteDraft(saved) {
  if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return null;
  const result = { ...blank };
  for (const field of ['task_number', 'origin', 'destination', 'mobile_origin']) {
    if (typeof saved[field] === 'string') result[field] = saved[field];
  }
  for (const field of ['origin_country', 'destination_country', 'mobile_origin_country']) {
    if (['UY', 'AR', 'BR'].includes(saved[field])) result[field] = saved[field];
  }
  for (const field of ['origin', 'destination', 'mobile_origin']) {
    if (['address', 'coordinates'].includes(saved[`${field}_entry_mode`])) result[`${field}_entry_mode`] = saved[`${field}_entry_mode`];
    else if (isDirectLocation(result[field])) result[`${field}_entry_mode`] = 'coordinates';
    if (saved[`${field}_confirmed`] === true && /^\s*-?\d{1,2}(?:\.\d+)?\s*,\s*-?\d{1,3}(?:\.\d+)?\s*$/.test(result[field])) result[`${field}_confirmed`] = true;
  }
  if (['insured', 'uninsured'].includes(saved.coverage)) result.coverage = saved.coverage;
  for (const field of ['special', 'gavilan', 'include_mobile', 'include_tolls']) {
    if (typeof saved[field] === 'boolean') result[field] = saved[field];
  }
  for (const field of ['manual_trip_km', 'manual_mobile_km', 'manual_toll_count']) {
    if (saved[field] !== null && Number.isFinite(saved[field]) && saved[field] >= 0) result[field] = saved[field];
  }
  if (result.special && result.gavilan) result.gavilan = false;
  return { ...result, mode: saved.mode === 'manual' ? 'manual' : 'automatic' };
}
