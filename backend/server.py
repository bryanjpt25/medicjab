"""Servidor local FastAPI: API REST + WebSocket + frontend estático.

    python run.py            ->  http://127.0.0.1:8000

El runtime (backend/runtime.py) hace un tick por segundo y el resultado se empuja por WebSocket
a todos los navegadores conectados. El frontend solo dibuja; toda la lógica vive aquí.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .runtime import SimulationRuntime
from .scenarios import ASTRONAUTS, ORBITS, SCENARIOS

log = logging.getLogger("astro")
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
TICK_S = 1.0


class Hub:
    """Mantiene los WebSockets abiertos y difunde cada estado."""

    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def broadcast(self, payload: str):
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


rt: SimulationRuntime | None = None
hub = Hub()
wake = asyncio.Event()      # una acción del usuario fuerza un tick inmediato


async def sim_loop():
    while True:
        try:
            state = await asyncio.to_thread(rt.tick)
            await hub.broadcast(json.dumps(state, default=str))
        except Exception:
            log.exception("error en el tick de simulación")
        try:
            await asyncio.wait_for(wake.wait(), timeout=TICK_S)
        except asyncio.TimeoutError:
            pass
        wake.clear()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global rt
    rt = await asyncio.to_thread(SimulationRuntime)     # carga motores (puede tardar unos segundos)
    task = asyncio.create_task(sim_loop())
    yield
    task.cancel()


app = FastAPI(title="Astro Health Monitor", lifespan=lifespan)
# Permite abrir el frontend desde Live Server (otro puerto) apuntando a ?api=http://127.0.0.1:8000
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ScenarioIn(BaseModel):
    key: str


class ToggleIn(BaseModel):
    name: str
    value: bool


class NameIn(BaseModel):
    name: str


def _act(fn, *args):
    try:
        fn(*args)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"valor no válido: {e}")
    wake.set()
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": rt is not None, "modules": rt.modules if rt else {}}


@app.get("/api/state")
def get_state():
    if rt is None or rt.last_state is None:
        raise HTTPException(status_code=503, detail="iniciando")
    return rt.last_state


@app.get("/api/catalog")
def catalog():
    return {"scenarios": list(SCENARIOS), "orbits": list(ORBITS), "astronauts": list(ASTRONAUTS)}


@app.post("/api/scenario")
def set_scenario(body: ScenarioIn):
    return _act(rt.apply_scenario, body.key)


@app.post("/api/toggle")
def set_toggle(body: ToggleIn):
    return _act(rt.set_toggle, body.name, body.value)


@app.post("/api/astronaut")
def set_astronaut(body: NameIn):
    return _act(rt.set_astronaut, body.name)


@app.post("/api/orbit")
def set_orbit(body: NameIn):
    return _act(rt.set_orbit, body.name)


@app.post("/api/reset")
def reset():
    return _act(rt.reset_all)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        if rt and rt.last_state:
            await ws.send_text(json.dumps(rt.last_state, default=str))
        while True:
            await ws.receive_text()          # solo para detectar la desconexión
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)


# Debe ir al final: sirve index.html, css/, js/ y assets/
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
