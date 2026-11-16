// Local browser state. Physiological data does NOT live here: it arrives from the backend (state.last).
export const state = {
  last: null,                                   // last state received from the server
  organ: 'heart',                               // selected scanner region
  toggles: { noise: false, raw: true, ai: false },
  connected: false,
  selectsSynced: false
};
