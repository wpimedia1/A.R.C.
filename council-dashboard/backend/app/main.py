"""FastAPI surface: health, run trigger, live websocket event feed, maps."""
from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DOTENV_FOUND = load_dotenv(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from . import events as E
from .agents import (
    DOMAIN_EXPERTS,
    OPEN_API_KEY,
    OPEN_BASE_URL,
    OPEN_KEY_FROM,
    OPEN_KEY_HINT,
    OPEN_MODEL,
    SMART_API_KEY,
    SMART_BASE_URL,
    SMART_KEY_FROM,
    SMART_KEY_HINT,
    SMART_MODEL,
    offline,
)
from .council import DATA_DIR, run_council
from .mars import SCENARIOS

@asynccontextmanager
async def _lifespan(app: FastAPI):
    print(f"[council] dotenv={DOTENV_FOUND} offline={offline()} "
          f"open={bool(OPEN_BASE_URL and OPEN_API_KEY)}:{OPEN_MODEL} "
          f"open_key={OPEN_KEY_FROM}:{OPEN_KEY_HINT} "
          f"smart={bool(SMART_BASE_URL and SMART_API_KEY)}:{SMART_MODEL} "
          f"smart_key={SMART_KEY_FROM}:{SMART_KEY_HINT}",
          flush=True)
    yield


app = FastAPI(title="Mars Council", lifespan=_lifespan)
listeners: List[WebSocket] = []
LAST_MAP: dict = {}

ALL_EVENTS = (
    E.RUN_STARTED, E.MODE_SELECTED, E.EVENT_START_ROUND_1, E.ROUND_1_SUBMIT,
    E.EVENT_START_ROUND_2, E.COUNTERARGUE, E.CLUSTER_FORMED,
    E.EVENT_START_ROUND_3, E.STEER_APPLIED, E.VOTE_CAST,
    E.CONSENSUS_REACHED, E.DISSENT_LOGGED, E.RUN_FINISHED,
    E.AUDIO_INGESTED, E.DAMAGE_ZONES, E.MAP_GENERATED,
    E.TOOL_REPAIRED, E.DEVIL_VERDICT, E.WONDER_PATHS,
)


class CustomScenario(BaseModel):
    title: str = Field(default="Custom decision")
    crisis: str = Field(min_length=10, max_length=2000)
    options: List[str] = Field(min_length=2, max_length=4)
    experts: List[str] = Field(
        default=["power_chief", "water_engineer", "logistics_coord"])
    irreversible: bool = Field(default=True)


class RunRequest(BaseModel):
    scenario: str = Field(default="reactor-failure")
    replay: bool = Field(default=False)
    audio_path: Optional[str] = Field(default=None)
    image_path: Optional[str] = Field(default=None)
    custom: Optional[CustomScenario] = Field(default=None)


@app.get("/health")
def health():
    env_path = os.path.normpath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".env"))
    return {"ok": True, "scenarios": sorted(SCENARIOS.keys()),
            "offline": offline(), "dotenv_found": bool(DOTENV_FOUND),
            "env_file": env_path, "env_file_exists": os.path.exists(env_path),
            "smart_inherit": True,
            "tiers": {
                "open": {"configured": bool(OPEN_BASE_URL and OPEN_API_KEY),
                         "model": OPEN_MODEL, "key_from": OPEN_KEY_FROM,
                         "key_hint": OPEN_KEY_HINT},
                "smart": {"configured": bool(SMART_BASE_URL and SMART_API_KEY),
                          "model": SMART_MODEL, "key_from": SMART_KEY_FROM,
                          "key_hint": SMART_KEY_HINT},
            }}


async def broadcast(event: E.Event) -> None:
    msg = event.to_json()
    dead = []
    for ws in listeners:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in listeners:
            listeners.remove(ws)


@app.post("/run")
async def run(req: RunRequest):
    key = req.scenario
    if req.custom is not None:
        options = [o.strip() for o in req.custom.options if o.strip()]
        if len(options) < 2:
            return JSONResponse({"error": "need at least 2 options"},
                                status_code=400)
        experts = [e for e in req.custom.experts if e in DOMAIN_EXPERTS]
        if not experts:
            experts = ["power_chief", "water_engineer", "logistics_coord"]
        scenario = {"title": req.custom.title[:80],
                    "crisis": req.custom.crisis,
                    "options": options, "experts": experts,
                    "irreversible": req.custom.irreversible, "shock": {}}
        key = "custom"
    elif req.scenario in SCENARIOS:
        scenario = SCENARIOS[req.scenario]
    else:
        return JSONResponse({"error": "unknown scenario"}, status_code=404)
    seed = int(os.environ.get("COUNCIL_SEED", "7"))
    bus = E.EventBus()
    for t in ALL_EVENTS:
        bus.subscribe(t, broadcast)
    try:
        result = await run_council(scenario, seed=seed,
                                   bus=bus, scenario_key=key,
                                   audio_path=req.audio_path,
                                   image_path=req.image_path,
                                   force_council=req.replay)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    LAST_MAP["path"] = result.map_artifact or None
    record = {"ts": time.time(), "scenario": key, "mode": result.mode,
              "action": result.action,
              "consensus": round(result.consensus, 3),
              "dissent_log": result.dissent_log,
              "live_model": result.live_model,
              "seed": seed, "events": len(bus.history)}
    try:
        with open(os.path.join(DATA_DIR, "runs.jsonl"), "a") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        record["persisted"] = False
    return {
        "mode": result.mode,
        "action": result.action,
        "consensus": round(result.consensus, 3),
        "dissent_log": result.dissent_log,
        "clusters": result.clusters,
        "silhouette": round(result.silhouette, 3),
        "steering": result.steering,
        "live_model": result.live_model,
        "wonder_paths": result.wonder_paths or [],
        "map": (result.map_artifact
                if result.map_artifact.startswith("http")
                else ("/map" if result.map_artifact else None)),
        "replay": req.replay,
    }


@app.get("/runs")
def run_history(limit: int = 20):
    path = os.path.join(DATA_DIR, "runs.jsonl")
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        lines = [ln for ln in fh if ln.strip()]
    out = []
    for ln in lines[-max(1, limit):]:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return list(reversed(out))


@app.get("/map")
def serve_map():
    path = LAST_MAP.get("path")
    if not path or not os.path.exists(path):
        return JSONResponse({"error": "no map generated yet"}, status_code=404)
    return FileResponse(path, media_type="image/svg+xml")


@app.websocket("/ws")
async def ws_feed(ws: WebSocket):
    await ws.accept()
    listeners.append(ws)
    try:
        while True:
            await asyncio.sleep(30.0)
            await ws.send_text(json.dumps({"type": "PING"}))
    except WebSocketDisconnect:
        pass
    finally:
        if ws in listeners:
            listeners.remove(ws)


OUT_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "frontend", "out"))
if os.path.isdir(OUT_DIR):
    app.mount("/", StaticFiles(directory=OUT_DIR, html=True),
              name="static")
