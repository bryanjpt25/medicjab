import sqlite3
import json
import time
from collections import deque

class JosePipelineEngine:
    def __init__(self, db_name="telemetry.db"):
        """
        Inicializa el motor de pipeline, base de datos SQLite local
        y el búfer FIFO para simular el modo BLACKOUT espacial.
        """
        self.db_name = db_name
        self.blackout_mode = False  # Interruptor de blackout
        self.fifo_buffer = deque()  # Cola FIFO local para almacenar datos durante el corte
        
        # Inicializar la base de datos SQLite
        self._init_db()

    def _init_db(self):
        """Crea la tabla SQLite para almacenar la telemetría histórica."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS telemetry_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                packet_json TEXT,
                synced INTEGER DEFAULT 1
            )
        ''')
        conn.commit()
        conn.close()

    def toggle_blackout(self, status: bool):
        """Activa o desactiva el modo BLACKOUT (pérdida de señal / desconexión)."""
        self.blackout_mode = status
        if not self.blackout_mode and len(self.fifo_buffer) > 0:
            # Si se desactiva el blackout, ejecutamos un proceso de retransmisión (Batch Flush)
            self._flush_buffer_to_db()

    def process_and_store_packet(self, telemetry_dict):
        """
        Recibe un paquete de telemetría (de Dick, Bryan o Denis).
        Si hay BLACKOUT activo, lo guarda en la cola FIFO local.
        Si no hay blackout, lo guarda directamente en la base de datos SQLite.
        """
        packet_str = json.dumps(telemetry_dict)
        timestamp = telemetry_dict.get("timestamp", time.time())

        if self.blackout_mode:
            # Modo Blackout: Acumular en memoria (Cola FIFO)
            self.fifo_buffer.append((timestamp, packet_str))
            return {
                "status": "BUFFERED_LOCAL", 
                "buffer_size": len(self.fifo_buffer),
                "message": "Blackout activo: Paquete retenido en búfer FIFO."
            }
        else:
            # Si veníamos de blackout y acabamos de vaciar el buffer, o flujo normal:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO telemetry_logs (timestamp, packet_json, synced) VALUES (?, ?, ?)",
                (timestamp, packet_str, 1)
            )
            conn.commit()
            conn.close()
            return {
                "status": "SAVED_ONLINE", 
                "buffer_size": len(self.fifo_buffer),
                "message": "Paquete transmitido y guardado en SQLite."
            }

    def _flush_buffer_to_db(self):
        """Proceso de retransmisión por lotes (Batch Flush) al recuperar la conexión."""
        if not self.fifo_buffer:
            return
        
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        batch_data = []
        while self.fifo_buffer:
            ts, pkt = self.fifo_buffer.popleft()
            batch_data.append((ts, pkt, 1)) # synced = 1
            
        cursor.executemany(
            "INSERT INTO telemetry_logs (timestamp, packet_json, synced) VALUES (?, ?, ?)",
            batch_data
        )
        conn.commit()
        conn.close()
        print(f"[PIPELINE PIPELINE]: Se sincronizaron {len(batch_data)} paquetes acumulados tras el Blackout.")

    def get_recent_history(self, limit=10):
        """Recupera los últimos registros guardados en SQLite para mostrarlos en gráficos de Streamlit."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, packet_json FROM telemetry_logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        history = []
        for ts, pkt in rows:
            data = json.loads(pkt)
            history.append(data)
        return history[::-1]  # Retornar en orden cronológico