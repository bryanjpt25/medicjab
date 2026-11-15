// Estado local del navegador. Los datos fisiológicos NO viven aquí: llegan del backend (state.last).
export const state = {
  last: null,                                   // último estado recibido del servidor
  organ: 'heart',                               // región del escáner seleccionada
  toggles: { noise: false, raw: true, ai: false },
  connected: false,
  selectsSynced: false
};
