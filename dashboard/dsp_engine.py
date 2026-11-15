import os
import time
import numpy as np
import pandas as pd
from scipy.signal import butter, iirnotch, filtfilt, find_peaks

class MedicJabDSPEngine:
    def __init__(self, fs=360.0):
        """
        Inicializa el motor DSP del proyecto MEDICJAB.
        :param fs: Frecuencia de muestreo en Hz (Por defecto 360 Hz para MIT-BIH).
        """
        self.fs = fs

    def load_ecg_from_csv(self, file_path="100.csv", column_name='MLII'):
        """
        Carga datos reales de ECG desde un archivo CSV.
        """
        try:
            if not os.path.exists(file_path) and os.path.exists(os.path.join("data", file_path)):
                file_path = os.path.join("data", file_path)

            df = pd.read_csv(file_path)
            if column_name not in df.columns:
                column_name = df.columns[1] if len(df.columns) > 1 else df.columns[0]
            
            signal = df[column_name].values.astype(float)
            return signal
        except Exception as e:
            print(f"Error al cargar el archivo CSV: {e}")
            return None

    def apply_cascade_filter(self, signal_raw):
        """
        Aplica el pipeline de filtrado digital en cascada (Notch 60Hz + Butterworth 0.5-40Hz)
        utilizando fase cero (filtfilt) para evitar distorsión temporal en los picos R.
        """
        # 1. Filtro Notch (60 Hz, Q = 30) para eliminar la interferencia eléctrica de la red
        b_notch, a_notch = iirnotch(w0=60.0, Q=30.0, fs=self.fs)
        notch_filtered = filtfilt(b_notch, a_notch, signal_raw)
        
        # 2. Filtro Pasa-Banda Butterworth (0.5 Hz a 40 Hz) para eliminar respiración y ruido muscular
        nyquist = 0.5 * self.fs
        lowcut = 0.5 / nyquist
        highcut = 40.0 / nyquist
        b_band, a_band = butter(2, [lowcut, highcut], btype='band')
        clean_signal = filtfilt(b_band, a_band, notch_filtered)
        
        return clean_signal

    def detect_qrs_pan_tompkins(self, ecg_filtered):
        """
        Algoritmo clásico de Pan-Tompkins para la detección precisa de picos R.
        """
        nyquist = 0.5 * self.fs
        
        # a) Filtro Pasa-banda específico de Pan-Tompkins (5 - 15 Hz)
        b_pt, a_pt = butter(1, [5.0 / nyquist, 15.0 / nyquist], btype='band')
        pt_filtered = filtfilt(b_pt, a_pt, ecg_filtered)
        
        # b) Derivada digital
        kernel_deriv = np.array([-1, -2, 0, 2, 1]) * (self.fs / 8.0)
        derived = np.convolve(pt_filtered, kernel_deriv, mode='same')
        
        # c) Elevación al cuadrado
        squared = derived ** 2
        
        # d) Integración por ventana móvil (150 ms)
        window_len = int(0.150 * self.fs)
        integrated = np.convolve(squared, np.ones(window_len) / window_len, mode='same')
        
        # e) Búsqueda de picos
        min_distance = int(0.4 * self.fs)
        peaks_integrated, _ = find_peaks(integrated, distance=min_distance, height=np.mean(integrated))
        
        r_peaks = []
        search_window = int(0.08 * self.fs)
        for p in peaks_integrated:
            start = max(0, p - search_window)
            end = min(len(ecg_filtered), p + search_window)
            r_peaks.append(start + np.argmax(ecg_filtered[start:end]))
            
        return np.array(r_peaks)

    def calculate_hrv_metrics(self, r_peaks):
        """
        Calcula las métricas estándar de Variabilidad de Frecuencia Cardíaca (HRV).
        """
        if len(r_peaks) < 2:
            return {"BPM": 0.0, "SDNN": 0.0, "RMSSD": 0.0, "status": "INSUFFICIENT_DATA"}
        
        rr_intervals = np.diff(r_peaks) * (1000.0 / self.fs)
        
        bpm = 60000.0 / np.mean(rr_intervals)
        sdnn = np.std(rr_intervals, ddof=1)
        
        rr_diff = np.diff(rr_intervals)
        rmssd = np.sqrt(np.mean(rr_diff ** 2)) if len(rr_diff) > 0 else 0.0
        
        if sdnn < 20.0 or bpm > 110:
            stress_status = "CRITICAL_ALERT"
        elif sdnn < 40.0 or bpm > 95:
            stress_status = "MODERATE_STRESS"
        else:
            stress_status = "NORMAL_STABLE"

        return {
            "BPM": float(round(bpm, 2)),
            "SDNN": float(round(sdnn, 2)),
            "RMSSD": float(round(rmssd, 2)),
            "status": stress_status
        }

    def process_pipeline(self, signal_raw):
        """
        Método ejecutor principal que une todo el flujo DSP.
        Mantiene las llaves originales para retrocompatibilidad y añade 
        las claves estandarizadas para Denis (IA) y Carlos (Dashboard).
        """
        filtered_ecg = self.apply_cascade_filter(signal_raw)
        r_peaks = self.detect_qrs_pan_tompkins(filtered_ecg)
        metrics = self.calculate_hrv_metrics(r_peaks)
        
        return {
            # Compatibilidad con código existente
            "filtered_ecg": filtered_ecg,
            "r_peaks": r_peaks,
            "metrics": metrics,
            
            # API Estandarizada para Dashboard (Carlos)
            "telemetry_output": {
                "timestamp": time.time(),
                "sampling_rate": self.fs,
                "raw_signal": signal_raw,
                "filtered_signal": filtered_ecg,
                "r_peaks_indices": r_peaks
            },
            
            # API Estandarizada para IA (Denis)
            "ai_features": {
                "bpm": metrics["BPM"],
                "sdnn": metrics["SDNN"],
                "rmssd": metrics["RMSSD"],
                "health_status": metrics["status"],
                "num_beats": len(r_peaks)
            }
        }

# Alias para mantener compatibilidad con scripts antiguos
AegisDSPEngine = MedicJabDSPEngine