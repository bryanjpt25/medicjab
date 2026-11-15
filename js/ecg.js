import { dataModes } from './scenarios.js';
import { state } from './state.js';

// Dibuja la señal ECG simulada y actualiza ligeramente FC y presión arterial.
export function startECG() {
  const canvas = document.getElementById('ecg-canvas');
  if (!canvas) return;
  const context = canvas.getContext('2d');
  if (!context) return;

  let offset = 0;

  function renderECG() {
    const width = canvas.width;
    const height = canvas.height;
    context.clearRect(0, 0, width, height);

    const scenario = dataModes[state.currentMode];
    context.strokeStyle = scenario.fcClass === 'crit' ? '#ef4444'
      : (scenario.fcClass === 'warn' ? '#f59e0b' : '#22c55e');
    context.lineWidth = 1.8;
    context.beginPath();
    offset += scenario.fc / 38;

    for (let x = 0; x < width; x++) {
      const cycle = (x + offset) % 72;
      let y = height * 0.55;

      if (state.rawSignal) {
        if (cycle > 10 && cycle < 17) y -= Math.sin(((cycle - 10) / 7) * Math.PI) * 4;
        else if (cycle >= 21 && cycle < 24) y += 5;
        else if (cycle >= 24 && cycle < 28) y -= 20;
        else if (cycle >= 28 && cycle < 32) y += 8;
        else if (cycle >= 40 && cycle < 52) y -= Math.sin(((cycle - 40) / 12) * Math.PI) * 6;
      }

      if (state.noiseActive) y += (Math.random() - 0.5) * 7;
      if (x === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    }

    context.stroke();
    requestAnimationFrame(renderECG);
  }

  renderECG();

  setInterval(() => {
    const scenario = dataModes[state.currentMode];
    const heartRateJitter = Math.floor(Math.random() * 5) - 2;
    const systolicJitter = Math.floor(Math.random() * 3) - 1;
    const diastolicJitter = Math.floor(Math.random() * 3) - 1;
    document.getElementById('val-fc').textContent = scenario.fc + heartRateJitter;
    document.getElementById('val-pa').textContent = `${scenario.pa[0] + systolicJitter}/${scenario.pa[1] + diastolicJitter}`;
  }, 1500);
}
