import { defaultOrganText, organLabels } from './scenarios.js';
import { state } from './state.js';
import { post } from './api.js';

const byId = id => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function fail(error) { console.error(error); }

// ---------------------------------------------------------------- actions sent to the backend
export function toggleSw(name) {
  state.toggles[name] = !state.toggles[name];     // optimistic; the server confirms in the next state
  paintToggles();
  post('/toggle', { name, value: state.toggles[name] }).catch(fail);
}

export function applyHazard(key) {
  post('/scenario', { key }).catch(fail);
}

export function selectOrgan(part) {
  state.organ = part;
  paintOrgan();
}

// ---------------------------------------------------------------- rendering
function setCard(id, val, stateClass, desc) {
  const card = byId('card-' + id);
  if (card) card.className = 'v-card ' + (stateClass || '');
  const valueElement = byId('val-' + id);
  if (valueElement) valueElement.textContent = val;
  const descriptionElement = byId('desc-' + id);
  if (descriptionElement && desc !== undefined) descriptionElement.textContent = desc;
}

function paintToggles() {
  byId('sw-noise').classList.toggle('active', state.toggles.noise);
  byId('sw-raw').classList.toggle('active', state.toggles.raw);
  byId('sw-ai').classList.toggle('active', state.toggles.ai);
  byId('card-ia').style.opacity = state.toggles.ai ? '1' : '0.45';
}

function paintOrgan() {
  byId('organ-head').textContent = organLabels[state.organ];
  byId('organ-body').textContent = state.last?.organs?.[state.organ] || defaultOrganText;
}

function paintHazards(s) {
  document.querySelectorAll('.ctrl-btn').forEach(button =>
    button.classList.remove('selected-crit', 'selected-warn', 'selected-ok'));
  const button = document.querySelector(`[data-hazard="${s.scenario}"]`);
  if (!button) return;
  button.classList.add(s.banner.cls === 'critico' ? 'selected-crit'
    : (s.banner.cls === 'alerta' ? 'selected-warn' : 'selected-ok'));
}

function paintAiHelper(s) {
  const helper = byId('ai-helper');
  const status = s.modules.ai;
  const base = 'Autonomous triage engine calibrated with NASA HRP ranges.';
  if (!state.toggles.ai) helper.textContent = base;
  else if (status === 'loading') helper.textContent = 'Loading TFLite model (the first time takes a while)…';
  else if (status === 'unavailable') helper.textContent = 'CNN unavailable (install tensorflow-cpu). Rule-based triage active.';
  else helper.textContent = base;
}

export function setConnection(connected) {
  state.connected = connected;
  byId('conn-badge').classList.toggle('offline', !connected);
  byId('conn-text').textContent = connected
    ? 'Local backend: CONNECTED'
    : 'No connection to backend… retrying';
}

export function render(s) {
  state.last = s;
  const v = s.vitals;

  // The selectors are synced only once (on page reload); after that the user is in control
  if (!state.selectsSynced) {
    byId('astro-select').value = s.selection.astro;
    byId('orbit-select').value = s.selection.orbit;
    state.selectsSynced = true;
  }

  // The server is the source of truth for the toggles
  state.toggles = { ...s.toggles };
  paintToggles();
  paintAiHelper(s);

  // Banner and Earth link
  byId('banner-box').className = 'status-banner ' + s.banner.cls;
  byId('banner-state').textContent = s.banner.text;
  byId('banner-meta').textContent = s.banner.meta;
  byId('comms-title').textContent = s.comms.title;
  byId('comms-sub').textContent = s.comms.sub;

  // Vital signs
  setCard('fc', v.fc.val, v.fc.cls, `${v.fc.desc} · SpO₂ ${v.spo2.val}%`);
  setCard('pa', v.pa.val, v.pa.cls, v.pa.desc);
  setCard('glu', v.glu.val, v.glu.cls, v.glu.desc);
  setCard('temp', v.temp.val, v.temp.cls, v.temp.desc);
  setCard('animo', v.animo.val, v.animo.cls, v.animo.desc);
  setCard('rad', v.rad.val, v.rad.cls, v.rad.desc);

  byId('val-sueno').textContent = Number(v.sueno.val).toFixed(1);
  const ring = byId('ring-sueno');
  ring.style.strokeDasharray = `${Math.min(v.sueno.val / 8, 1) * 220} 280`;
  ring.style.stroke = v.sueno.color;

  byId('card-ia').className = 'v-card ' + v.ia.cls;
  byId('val-ia').textContent = v.ia.title;
  byId('desc-ia').textContent = v.ia.desc;
  paintToggles();

  // Body scanner
  byId('pt-heart').className.baseVal = 'node-point ' + s.points.heart;
  byId('pt-abdomen').className.baseVal = 'node-point ' + s.points.abdomen;
  byId('pt-legL').className.baseVal = 'node-point ' + s.points.legs;
  byId('pt-legR').className.baseVal = 'node-point ' + s.points.legs;
  paintOrgan();
  paintHazards(s);

  renderAlerts(s);
  renderTwin(s);
  renderOrbital(s);
  renderGateway(s);
  renderModules(s);
}

// ---------------------------------------------------------------- operations panel
function renderAlerts(s) {
  const list = byId('alerts-list');
  list.replaceChildren();
  byId('alerts-count').textContent = `${s.alerts.length} active`;
  if (!s.alerts.length) {
    list.appendChild(el('li', 'al-ok', 'All vital signs and cabin readings are within normal range.'));
    return;
  }
  const shown = new Set();
  s.alerts.forEach(alert => {
    const item = el('li', alert.level === 'error' ? 'al-err' : 'al-warn', alert.msg);
    if (alert.protocol && !shown.has(alert.protocol)) {
      shown.add(alert.protocol);
      const details = el('details', 'al-protocol');
      details.appendChild(el('summary', '', `Automatic protocol (${alert.protocol})`));
      const steps = el('ol');
      alert.steps.forEach(step => steps.appendChild(el('li', '', step)));
      details.appendChild(steps);
      item.appendChild(details);
    }
    list.appendChild(item);
  });
}

function stat(label, value) {
  const box = el('div', 'ops-stat');
  box.appendChild(el('span', 'ops-label', label));
  box.appendChild(el('strong', '', value));
  return box;
}

function renderTwin(s) {
  const body = byId('twin-body');
  body.replaceChildren();
  const tw = s.twin;
  if (!tw) {
    body.appendChild(el('p', 'ops-note', 'Bio-digital twin unavailable.'));
    if (s.modules.twin_error) body.appendChild(el('p', 'ops-note mono', s.modules.twin_error));
    return;
  }
  if (tw.error) { body.appendChild(el('p', 'ops-note', tw.error)); return; }
  const grid = el('div', 'ops-stats');
  grid.append(stat('Global level', tw.level), stat('SHARE', tw.share_index.toFixed(2)),
    stat('Anomaly', tw.anomaly.toFixed(2)), stat('S.H.A.R.E. step', tw.step || '—'));
  body.appendChild(grid);
  const bar = el('div', 'ops-bar');
  const fill = el('div', 'ops-bar-fill');
  fill.style.width = `${Math.min(tw.share_index * 100, 100)}%`;
  bar.appendChild(fill);
  body.appendChild(bar);
  if (tw.requires_clinician) {
    body.appendChild(el('p', 'ops-warn', 'Clinical confirmation required (CMO / flight surgeon).'));
  }
  if (tw.options?.length) {
    body.appendChild(el('p', 'ops-label', 'Proposed countermeasures'));
    const list = el('ul', 'ops-options');
    tw.options.forEach(option => {
      const item = el('li');
      item.appendChild(el('strong', '', option.label + (option.clinician ? ' · requires physician' : '')));
      item.appendChild(el('span', '', ' ' + option.benefits));
      list.appendChild(item);
    });
    body.appendChild(list);
  }
}

function renderOrbital(s) {
  const body = byId('orbital-body');
  body.replaceChildren();
  const o = s.orbital;
  if (!s.modules.orbital) {
    body.appendChild(el('p', 'ops-note', 'Orbital engine unavailable.'));
    return;
  }
  const delay = o.delay_s < 60 ? `${o.delay_s.toFixed(1)} s` : `${(o.delay_s / 60).toFixed(0)} min`;
  const grid = el('div', 'ops-stats');
  grid.append(stat('Global risk', `${o.risk}/100`), stat('Zone', o.zone),
    stat('Cum. dose', `${o.cum_msv.toFixed(0)} mSv · ${o.limit_pct.toFixed(0)}%`),
    stat('One-way delay', `${delay} · auton. ${o.autonomy_pct.toFixed(0)}%`));
  body.appendChild(grid);
  o.anomalies.forEach(a => body.appendChild(el('p', 'ops-anomaly', `[${a.sev}] ${a.code}: ${a.detail}`)));
}

function renderGateway(s) {
  const body = byId('gateway-body');
  body.replaceChildren();
  const g = s.gateway;
  if (g.kind === 'none') { body.appendChild(el('p', 'ops-note', 'Gateway unavailable.')); return; }
  const grid = el('div', 'ops-stats');
  grid.append(stat('Stored', g.total), stat('In FIFO', g.pending),
    stat('Received by Earth', g.earth), stat('Link', g.blackout ? 'BLACKOUT' : 'ACTIVE'));
  body.appendChild(grid);
  body.appendChild(el('p', 'ops-note mono', `Mode: ${g.kind}`));
  g.rows.slice().reverse().forEach(row => {
    body.appendChild(el('p', 'ops-row mono',
      `${row.t} · ${row.scenario} · ${row.hr ?? '—'} bpm · ${row.forwarded ? '✅ sent' : '⏳ in FIFO'}`));
  });
  if (g.error) body.appendChild(el('p', 'ops-note mono', g.error));
}

function renderModules(s) {
  const m = s.modules;
  byId('modules-line').textContent = [
    `ECG: ${m.ecg_source === 'mit-bih' ? 'MIT-BIH (100.csv)' : 'synthetic (data/100.csv not found)'}`,
    `AI: ${m.ai}`,
    `Twin: ${m.twin ? 'ok' : 'unavailable'}`,
    `Orbital: ${m.orbital ? 'ok' : 'unavailable'}`,
    `Gateway: ${m.gateway}`
  ].join('  ·  ');
}

// ---------------------------------------------------------------- initialization
export function initUI() {
  byId('astro-select').addEventListener('change', event =>
    post('/astronaut', { name: event.target.value }).catch(fail));
  byId('orbit-select').addEventListener('change', event =>
    post('/orbit', { name: event.target.value }).catch(fail));

  document.querySelectorAll('[data-toggle]').forEach(element => {
    element.addEventListener('click', () => toggleSw(element.dataset.toggle));
    element.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleSw(element.dataset.toggle);
      }
    });
  });

  document.querySelectorAll('[data-hazard]').forEach(button =>
    button.addEventListener('click', () => applyHazard(button.dataset.hazard)));

  document.querySelectorAll('[data-organ]').forEach(point => {
    point.addEventListener('click', () => selectOrgan(point.dataset.organ));
    point.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectOrgan(point.dataset.organ);
      }
    });
  });

  byId('btn-reset').addEventListener('click', () => post('/reset').catch(fail));
  paintToggles();
  paintOrgan();
}
