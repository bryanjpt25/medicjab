import { dataModes } from './scenarios.js';
import { state } from './state.js';

function byId(id) {
  return document.getElementById(id);
}

export function toggleSw(id) {
  if (id === 'noise') {
    state.noiseActive = !state.noiseActive;
    byId('sw-noise').classList.toggle('active', state.noiseActive);
  } else if (id === 'raw') {
    state.rawSignal = !state.rawSignal;
    byId('sw-raw').classList.toggle('active', state.rawSignal);
  } else if (id === 'ai') {
    state.aiActive = !state.aiActive;
    byId('sw-ai').classList.toggle('active', state.aiActive);
    byId('card-ia').style.opacity = state.aiActive ? '1' : '0.45';
  }
}

export function updateMeta() {
  const astro = byId('astro-select').value;
  const orbit = byId('orbit-select').value;
  const role = astro === 'Cmdr. Rivera' ? 'Comandante'
    : (astro === 'Dra. Vance' ? 'Médico' : 'Ingeniero');
  byId('banner-meta').textContent = `${astro} · ${role} · ${orbit} · Día 45 · T+266:09`;
}

function setCard(id, val, stateClass, desc) {
  const card = byId('card-' + id);
  if (card) card.className = 'v-card ' + stateClass;
  const valueElement = byId('val-' + id);
  if (valueElement) valueElement.textContent = val;
  const descriptionElement = byId('desc-' + id);
  if (descriptionElement) descriptionElement.textContent = desc;
}

export function selectOrgan(part) {
  const labels = {
    heart: 'Diagnóstico Regional: Tórax / Cardíaco',
    abdomen: 'Diagnóstico Regional: Abdomen / Metabólico',
    legs: 'Diagnóstico Regional: Extremidades / Retorno Venoso'
  };
  byId('organ-head').textContent = labels[part];
  byId('organ-body').textContent = dataModes[state.currentMode].organs[part];
}

export function applyHazard(key, button) {
  state.currentMode = key;
  document.querySelectorAll('.ctrl-btn').forEach(element => {
    element.classList.remove('selected-crit', 'selected-warn', 'selected-ok');
  });

  const scenario = dataModes[key];
  if (!scenario) return;

  const selectedButton = button || document.querySelector(`[data-hazard="${key}"]`);
  if (scenario.bannerClass === 'critico') selectedButton?.classList.add('selected-crit');
  else if (scenario.bannerClass === 'alerta') selectedButton?.classList.add('selected-warn');
  else selectedButton?.classList.add('selected-ok');

  const banner = byId('banner-box');
  banner.className = 'status-banner ' + scenario.bannerClass;
  byId('banner-state').textContent = scenario.bannerText;
  updateMeta();

  byId('comms-title').textContent = scenario.commsTitle;
  byId('comms-sub').textContent = scenario.commsSub;

  setCard('fc', scenario.fc, scenario.fcClass, scenario.fcDesc);
  setCard('pa', `${scenario.pa[0]}/${scenario.pa[1]}`, scenario.paClass, scenario.paDesc);
  setCard('glu', scenario.glu, scenario.gluClass, scenario.gluDesc);
  setCard('temp', scenario.temp, scenario.tempClass, scenario.tempDesc);
  setCard('animo', scenario.animoVal, scenario.animoClass, scenario.animoDesc);
  setCard('rad', scenario.radVal, scenario.radClass, scenario.radDesc);

  byId('val-sueno').textContent = scenario.sueno.toFixed(1);
  const ring = byId('ring-sueno');
  const arc = Math.min(scenario.sueno / 8, 1) * 220;
  ring.style.strokeDasharray = `${arc} 280`;
  ring.style.stroke = scenario.suenoColor;

  const iaCard = byId('card-ia');
  iaCard.className = 'v-card ' + scenario.iaClass;
  byId('val-ia').textContent = scenario.iaTitle;
  byId('desc-ia').textContent = scenario.iaDesc;

  byId('pt-heart').className.baseVal = 'node-point ' + scenario.pts.heart;
  byId('pt-abdomen').className.baseVal = 'node-point ' + scenario.pts.abdomen;
  byId('pt-legL').className.baseVal = 'node-point ' + scenario.pts.legs;
  byId('pt-legR').className.baseVal = 'node-point ' + scenario.pts.legs;

  selectOrgan('heart');
}

export function initUI() {
  byId('astro-select').addEventListener('change', updateMeta);
  byId('orbit-select').addEventListener('change', updateMeta);

  document.querySelectorAll('[data-toggle]').forEach(element => {
    element.addEventListener('click', () => toggleSw(element.dataset.toggle));
    element.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleSw(element.dataset.toggle);
      }
    });
  });

  document.querySelectorAll('[data-hazard]').forEach(button => {
    button.addEventListener('click', () => applyHazard(button.dataset.hazard, button));
  });

  document.querySelectorAll('[data-organ]').forEach(point => {
    point.addEventListener('click', () => selectOrgan(point.dataset.organ));
    point.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectOrgan(point.dataset.organ);
      }
    });
  });
}
