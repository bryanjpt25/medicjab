import { state } from './state.js';

// Real ECG: backend filters with DSP (notch 60 Hz + Butterworth + Pan-Tompkins)
// and sends ~120 samples every second (raw + filtered, already normalized). Here they are only replayed
// in real-time with a continuous scroll.
const RING = 480;                       // 4 s at 120 Hz
const ringRaw = new Array(RING).fill(0);
const ringFilt = new Array(RING).fill(0);
const queue = [];
let fs = 120;

export function pushEcg(ecg) {
  if (!ecg || !ecg.filt) return;
  fs = ecg.fs || fs;
  for (let i = 0; i < ecg.filt.length; i++) queue.push([ecg.raw[i], ecg.filt[i]]);
  if (queue.length > fs * 3) queue.splice(0, queue.length - fs * 2);   // avoids accumulating lag (background tab)
}

export function startECG() {
  const canvas = document.getElementById('ecg-canvas');
  if (!canvas) return;
  const context = canvas.getContext('2d');
  if (!context) return;

  let last = performance.now();
  let credit = 0;

  function frame(now) {
    const dt = Math.min(0.25, (now - last) / 1000);
    last = now;
    credit += dt * fs * (queue.length > fs * 1.5 ? 1.3 : 1);
    while (credit >= 1 && queue.length) {
      const [raw, filt] = queue.shift();
      ringRaw.push(raw); ringRaw.shift();
      ringFilt.push(filt); ringFilt.shift();
      credit -= 1;
    }
    if (!queue.length) credit = Math.min(credit, 1);
    draw(context, canvas);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function trace(context, data, width, height, color, lineWidth, alpha) {
  const mid = height * 0.55;
  const amp = height * 0.36;
  context.globalAlpha = alpha;
  context.strokeStyle = color;
  context.lineWidth = lineWidth;
  context.beginPath();
  for (let i = 0; i < data.length; i++) {
    const x = (i / (data.length - 1)) * width;
    const v = Math.max(-1.4, Math.min(1.4, data[i]));
    const y = mid - v * amp;
    if (i === 0) context.moveTo(x, y); else context.lineTo(x, y);
  }
  context.stroke();
  context.globalAlpha = 1;
}

function draw(context, canvas) {
  const { width, height } = canvas;
  context.clearRect(0, 0, width, height);
  const cls = state.last?.vitals?.fc?.cls;
  const color = cls === 'crit' ? '#ef4444' : (cls === 'warn' ? '#f59e0b' : '#22c55e');
  if (state.toggles.raw) trace(context, ringRaw, width, height, '#64748b', 1.2, 0.75);   // raw signal (gray)
  trace(context, ringFilt, width, height, color, 2, 1);                                    // filtered signal
}