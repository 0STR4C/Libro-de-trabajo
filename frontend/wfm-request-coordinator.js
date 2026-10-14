const keyFor = (day, team) => `${day}\u0000${team}`;

// Mantiene la pertenencia de cada respuesta al día, equipo y revisión que la inició.
// No cancela escrituras: evita que una respuesta tardía reemplace otra vista.
export function createWfmRequestCoordinator(initial) {
  let context = {
    day: initial.day,
    team: initial.team,
    revision: Number(initial.revision || 0),
    key: keyFor(initial.day, initial.team),
    generation: 0,
    editVersion: 0,
  };
  let loadSequence = 0;
  let mutationSequence = 0;
  let mutation = null;

  return {
    get context() { return { ...context }; },
    get pendingMutation() { return mutation ? { ...mutation } : null; },
    markEdited() { context = { ...context, editVersion: context.editVersion + 1 }; },
    beginLoad(day, team) {
      loadSequence += 1;
      context = { ...context, generation: context.generation + 1 };
      return { id: loadSequence, day, team, key: keyFor(day, team) };
    },
    isLoadCurrent(token) { return token.id === loadSequence; },
    acceptLoad(token, revision) {
      if (token.id !== loadSequence) return false;
      context = {
        day: token.day,
        team: token.team,
        revision: Number(revision || 0),
        key: token.key,
        generation: context.generation + 1,
        editVersion: 0,
      };
      return true;
    },
    beginMutation(kind) {
      if (mutation) return null;
      mutation = {
        id: ++mutationSequence,
        kind,
        day: context.day,
        team: context.team,
        key: context.key,
        revision: context.revision,
        generation: context.generation,
        editVersion: context.editVersion,
      };
      return { ...mutation };
    },
    isMutationCurrent(token) {
      return Boolean(
        mutation && mutation.id === token.id
        && context.key === token.key
        && context.revision === token.revision
        && context.generation === token.generation
        && context.editVersion === token.editVersion
      );
    },
    acceptMutation(token, revision) {
      if (!this.isMutationCurrent(token)) return false;
      context = { ...context, revision: Number(revision ?? context.revision), editVersion: 0 };
      return true;
    },
    finishMutation(token) {
      if (mutation?.id === token?.id) mutation = null;
    },
  };
}

export function wfmResponseMatches(response, token) {
  return Boolean(response)
    && String(response.plan_date || token.day) === token.day
    && String(response.team || token.team) === token.team;
}
