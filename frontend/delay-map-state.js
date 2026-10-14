// Reevalúa el vencimiento con el reloj actual, aun si el mapa sigue abierto.
export function isDelayReviewDue(delay, now = Date.now()) {
  const deadline = Date.parse(delay.review_due_at || '');
  return delay.needs_review === true || !Number.isFinite(deadline) || deadline <= now;
}

export function departmentAt(department, now = Date.now()) {
  if (!department) return null;
  const delays = (department.delays || []).map(delay => ({
    ...delay,
    needs_review: isDelayReviewDue(delay, now)
  }));
  const review_due_count = delays.filter(delay => delay.needs_review).length;
  return {
    ...department,
    delays,
    active_count: delays.length,
    review_due_count,
    verified_count: delays.length - review_due_count
  };
}

export function nextReviewDeadline(mapStats, now = Date.now()) {
  const deadlines = (mapStats?.departments || []).flatMap(department => department.delays || [])
    .filter(delay => !isDelayReviewDue(delay, now))
    .map(delay => Date.parse(delay.review_due_at));
  return deadlines.length ? Math.min(...deadlines) : null;
}
