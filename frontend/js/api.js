// Comunicación con el backend (FastAPI). Mismo origen por defecto.
// Si abres el HTML con Live Server (otro puerto), usa:  index.html?api=http://127.0.0.1:8000
const BASE = (new URLSearchParams(location.search).get('api') || '').replace(/\/$/, '');

export async function post(path, body = {}) {
  const response = await fetch(`${BASE}/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

export function connect(onState, onStatus) {
  const origin = BASE || location.origin;
  const url = origin.replace(/^http/, 'ws') + '/ws';

  function open() {
    const socket = new WebSocket(url);
    socket.onopen = () => onStatus(true);
    socket.onmessage = event => onState(JSON.parse(event.data));
    socket.onclose = () => { onStatus(false); setTimeout(open, 1500); };
    socket.onerror = () => socket.close();
  }
  open();
}
