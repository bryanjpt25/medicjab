"""Local FastAPI Server: REST API + WebSocket + Static Frontend.

    python run.py            ->  http://127.0.0.1:8000
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .runtime import SimulationRuntime
from .scenarios import ASTRONAUTS, ORBITS, SCENARIOS

log = logging.getLogger("medicjab")
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
TICK_S = 1.0


class Hub:
    """Manages open WebSocket clients and broadcasts state updates."""

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
wake = asyncio.Event()


async def sim_loop():
    while True:
        try:
            state = await asyncio.to_thread(rt.tick)
            await hub.broadcast(json.dumps(state, default=str))
        except Exception:
            log.exception("Error in simulation tick")
        try:
            await asyncio.wait_for(wake.wait(), timeout=TICK_S)
        except asyncio.TimeoutError:
            pass
        wake.clear()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global rt
    rt = await asyncio.to_thread(SimulationRuntime)
    task = asyncio.create_task(sim_loop())
    yield
    task.cancel()


app = FastAPI(title="MEDICJAB", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ScenarioIn(BaseModel):
    key: str


class ToggleIn(BaseModel):
    name: str
    value: bool


class NameIn(BaseModel):
    name: str


class IngestIn(BaseModel):
    crew_id: Optional[str] = None
    timestamp: Optional[str] = None
    psych: Optional[dict[str, Any]] = None


def _act(fn, *args):
    try:
        fn(*args)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"Invalid value: {e}")
    wake.set()
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": rt is not None, "modules": rt.modules if rt else {}}


@app.get("/api/state")
def get_state():
    if rt is None or rt.last_state is None:
        raise HTTPException(status_code=503, detail="Initializing system...")
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


@app.post("/api/ingest")
def ingest_psych_test(body: IngestIn):
    """Receives psychological assessment scores (PHQ-9 / GAD-7) from evaluacion.html."""
    log.info(f"Received psychological assessment for {body.crew_id}: {body.psych}")
    return {"ok": True, "message": "Psychological assessment processed successfully"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        if rt and rt.last_state:
            await ws.send_text(json.dumps(rt.last_state, default=str))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")