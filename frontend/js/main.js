// Punto de entrada: conecta interfaz, ECG y backend.
import { connect } from './api.js';
import { initUI, render, setConnection } from './ui.js';
import { pushEcg, startECG } from './ecg.js';

initUI();
startECG();
connect(snapshot => { pushEcg(snapshot.ecg); render(snapshot); }, setConnection);
