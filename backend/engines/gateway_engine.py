"""Gateway local AEGIS (Jose): MQTT -> SQLite (WAL) -> búfer FIFO -> reenvío QoS 1."""
import json
import sqlite3
import threading
import time
import uuid
from collections import deque

import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
PORT = 1883
TOPIC_SUBSCRIBE = "aegis/+/telemetry"
TOPIC_FORWARD = "server/aegis/telemetry"   # "la Tierra"
DB_FILE = "local_buffer.db"
FORWARD_DELAY = 0.05                        # pausa entre envíos para ver vaciarse el FIFO


def new_client(name, clean_session=True):
    """Compatible con paho-mqtt 1.x y 2.x. Id único para no chocar al recargar."""
    cid = f"{name}_{uuid.uuid4().hex[:6]}"
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid,
                           clean_session=clean_session)
    except AttributeError:
        return mqtt.Client(client_id=cid, clean_session=clean_session)


def setup_db():
    """SQLite con modo WAL y protección contra duplicados."""
    conn = sqlite3.connect(DB_FILE, isolation_level=None, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=FULL;")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS telemetry_fifo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crew_id TEXT,
            timestamp TEXT,
            payload TEXT,
            forwarded INTEGER DEFAULT 0,
            UNIQUE(crew_id, timestamp)
        )
    ''')
    return conn


class GatewayEngine:
    def __init__(self):
        self.blackout = False
        self.earth_count = 0                 # paquetes recibidos por "la Tierra" en esta sesión
        self.earth_last = deque(maxlen=10)
        self.last_error = None
        setup_db().close()

        # 1) Sensor: publica la telemetría del dashboard
        self.sensor = new_client("Dashboard_Sensor")
        self.sensor.connect(BROKER, PORT, 60)
        self.sensor.loop_start()

        # 2) Receptor: MQTT -> SQLite
        self.receiver = new_client("Gateway_Receiver")
        self.receiver.on_message = self._on_message
        self.receiver.on_connect = lambda c, u, *a: c.subscribe(TOPIC_SUBSCRIBE, qos=1)
        self.receiver.connect(BROKER, PORT, 60)
        self.receiver.loop_start()

        # 3) Forwarder: SQLite -> MQTT (QoS 1)
        self.forwarder = new_client("Gateway_Forwarder", clean_session=False)
        self.forwarder.connect(BROKER, PORT, 60)
        self.forwarder.loop_start()
        threading.Thread(target=self._forwarder_worker, daemon=True).start()

        # 4) "Tierra": recibe lo reenviado
        self.earth = new_client("Earth_Receiver")
        self.earth.on_message = self._on_earth
        self.earth.on_connect = lambda c, u, *a: c.subscribe(TOPIC_FORWARD, qos=1)
        self.earth.connect(BROKER, PORT, 60)
        self.earth.loop_start()

    # ---- API para el dashboard ----
    def publish_packet(self, packet):
        """El 'sensor' envía un paquete (siempre, haya o no blackout)."""
        info = self.sensor.publish(f"aegis/{packet['crew_id']}/telemetry",
                                   json.dumps(packet, default=str), qos=1)
        return info.rc

    def stats(self):
        conn = sqlite3.connect(DB_FILE, timeout=5)
        total, pending = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(forwarded=0),0) FROM telemetry_fifo").fetchone()
        conn.close()
        return {"total": total, "pending": int(pending), "forwarded": total - int(pending)}

    def recent(self, limit=6):
        conn = sqlite3.connect(DB_FILE, timeout=5)
        rows = conn.execute("SELECT payload, forwarded FROM telemetry_fifo "
                            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        out = []
        for payload, fwd in reversed(rows):
            d = json.loads(payload)
            d["_forwarded"] = bool(fwd)
            out.append(d)
        return out

    # ---- Hilos de Jose ----
    def _on_message(self, client, userdata, msg):
        """Guarda en SQLite; INSERT OR IGNORE descarta duplicados."""
        try:
            payload_str = msg.payload.decode("utf-8")
            data = json.loads(payload_str)
            conn = setup_db()
            conn.execute(
                "INSERT OR IGNORE INTO telemetry_fifo (crew_id, timestamp, payload) "
                "VALUES (?, ?, ?)",
                (data.get("crew_id", "UNKNOWN"), data.get("timestamp", "UNKNOWN"), payload_str))
            conn.close()
        except Exception as e:
            self.last_error = f"receptor: {e}"

    def _forwarder_worker(self):
        """Lee el registro más antiguo no enviado (FIFO) y lo reenvía con QoS 1."""
        conn = setup_db()
        while True:
            if self.blackout:
                time.sleep(0.5)      # sin enlace: SQLite sigue guardando, no se envía
                continue
            row = conn.execute("SELECT id, payload FROM telemetry_fifo "
                               "WHERE forwarded = 0 ORDER BY timestamp ASC LIMIT 1").fetchone()
            if not row:
                time.sleep(0.3)
                continue
            try:
                info = self.forwarder.publish(TOPIC_FORWARD, row[1], qos=1)
                info.wait_for_publish(timeout=5)
                if info.is_published():
                    conn.execute("UPDATE telemetry_fifo SET forwarded = 1 WHERE id = ?", (row[0],))
                    time.sleep(FORWARD_DELAY)
                else:
                    time.sleep(2)
            except Exception as e:
                self.last_error = f"forwarder: {e}"
                time.sleep(2)

    def _on_earth(self, client, userdata, msg):
        self.earth_count += 1
        try:
            self.earth_last.append(json.loads(msg.payload.decode("utf-8")))
        except Exception:
            pass