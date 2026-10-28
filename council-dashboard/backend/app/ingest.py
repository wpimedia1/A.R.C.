"""Multimodal ingestion layer.

Voice: dispatcher audio feeds are transcribed with Muse Voice Transcribe
into structured crisis telemetry events. Imagery: habitat visual feeds go
through SAM 3.1 for damage segmentation; zones route to Logistics and the
Medical Center agents.

Live-first rules: real audio/imagery call the live endpoints. Without
files, the Muse chat tier generates structured telemetry and zones from
the crisis brief as genuine model output (labeled live_model). The
bundled fixtures parse only in rehearsal mode (COUNCIL_OFFLINE=1).
Otherwise calls raise with remediation instead of inventing data.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

import httpx

from .agents import OPEN_API_KEY, OPEN_BASE_URL, OPEN_MODEL

META_HOST = "https://api.meta.ai"


def _key(*names: str) -> str:
    for name in names:
        val = os.environ.get(name, "")
        if val:
            return val
    return ""


VOICE_BASE_URL = os.environ.get("VOICE_BASE_URL", META_HOST)
VOICE_API_KEY = _key("VOICE_API_KEY", "OPEN_API_KEY", "SMART_API_KEY",
                     "MODEL_API_KEY")
VOICE_MODEL = os.environ.get("VOICE_MODEL", "muse-voice-transcribe-1.0")
SAM_BASE_URL = os.environ.get("SAM_BASE_URL", META_HOST)
SAM_API_KEY = _key("SAM_API_KEY", "OPEN_API_KEY", "SMART_API_KEY",
                   "MODEL_API_KEY")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

DISPATCH_RE = re.compile(
    r"DISPATCH\s+(\S+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(.+)"
)
SEV_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def offline() -> bool:
    return os.environ.get("COUNCIL_OFFLINE", "0") == "1"


def _chat_json(system: str, user: str) -> Dict[str, Any]:
    if not (OPEN_BASE_URL and OPEN_API_KEY):
        raise RuntimeError(
            "no model credentials: set OPEN_BASE_URL + OPEN_API_KEY "
            "(claim the $150 Meta Model API credit) or run with "
            "COUNCIL_OFFLINE=1 for rehearsal mode")
    resp = httpx.post(
        OPEN_BASE_URL.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {OPEN_API_KEY}"},
        json={"model": OPEN_MODEL,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}],
              "temperature": 0.2},
        timeout=60.0,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


def _parse_dispatch_lines(lines: List[str]) -> List[Dict[str, str]]:
    events = []
    for ln in lines:
        m = DISPATCH_RE.match(ln.strip())
        if m:
            events.append({
                "time": m.group(1), "facility": m.group(2).lower(),
                "severity": m.group(3), "text": m.group(4),
            })
    events.sort(key=lambda e: -SEV_RANK.get(e["severity"], 0))
    return events


def transcribe_dispatch_log(path: str | None = None,
                            crisis: str = "") -> Dict[str, Any]:
    if path and path.lower().endswith((".wav", ".mp3", ".m4a", ".ogg")):
        if not (VOICE_BASE_URL and VOICE_API_KEY):
            raise RuntimeError(
                "audio input needs VOICE_BASE_URL + VOICE_API_KEY")
        with open(path, "rb") as fh:
            settings = json.dumps(
                {"model": VOICE_MODEL, "audioEncoding": "WAV",
                 "mode": "PUSH_TO_TALK"})
            resp = httpx.post(
                VOICE_BASE_URL.rstrip("/") + "/v1/asr/transcribe",
                headers={"Authorization": f"Bearer {VOICE_API_KEY}",
                         "Accept": "application/json"},
                data={"request": settings},
                files={"audio": (os.path.basename(path), fh,
                                 "audio/wav")},
                timeout=60.0,
            )
            resp.raise_for_status()
            body = resp.json()
            text = (body.get("text") or body.get("transcript")
                    or body.get("transcription") or "")
            if not text:
                raise RuntimeError(
                    "voice endpoint returned no transcript field; body: "
                    f"{resp.text[:300]}")
        return {"transcript": text, "live_model": True, "source": path,
                "model": VOICE_MODEL}
    if path:
        with open(path) as fh:
            events = _parse_dispatch_lines([ln for ln in fh if ln.strip()])
        return {"telemetry": events, "live_model": False,
                "source": path, "note": "operator-supplied log parse"}
    if OPEN_BASE_URL and OPEN_API_KEY:
        data = _chat_json(
            "Emit JSON only: {\"entries\": [{\"time\": \"HH:MM:SS\", "
            "\"facility\": \"power|water|medical|logistics\", "
            "\"severity\": \"LOW|MEDIUM|HIGH|CRITICAL\", "
            "\"text\": \"<one line>\"}]}. Five entries.",
            f"Draft the dispatcher log for this Mars colony crisis: {crisis}")
        events = [{"time": e["time"], "facility": e["facility"],
                   "severity": e["severity"], "text": e["text"]}
                  for e in data.get("entries", [])]
        events.sort(key=lambda e: -SEV_RANK.get(e["severity"], 0))
        return {"telemetry": events, "live_model": True,
                "model": OPEN_MODEL, "note": "model-generated log"}
    if offline():
        with open(os.path.join(DATA_DIR, "dispatch_reactor.txt")) as fh:
            events = _parse_dispatch_lines([ln for ln in fh if ln.strip()])
        return {"telemetry": events, "live_model": False,
                "note": "rehearsal fixture"}
    raise RuntimeError(
        "no telemetry source: provide an audio/log path, set "
        "OPEN_BASE_URL + OPEN_API_KEY, or COUNCIL_OFFLINE=1")


def _bbox(polygon: List[List[float]]) -> List[float]:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return [min(xs), min(ys), max(xs), max(ys)]


def segment_damage(image_path: str | None = None,
                   crisis: str = "") -> Dict[str, Any]:
    if image_path and image_path.lower().endswith(
            (".png", ".jpg", ".jpeg", ".tif")):
        if not (SAM_BASE_URL and SAM_API_KEY):
            raise RuntimeError(
                "imagery input needs SAM_BASE_URL + SAM_API_KEY")
        import base64
        with open(image_path, "rb") as fh:
            raw = fh.read()
        ext = image_path.lower().rsplit(".", 1)[-1]
        mime = {"png": "image/png", "jpg": "image/jpeg",
                "jpeg": "image/jpeg", "tif": "image/tiff"}.get(ext,
                                                              "image/png")
        data_url = ("data:" + mime + ";base64,"
                    + base64.b64encode(raw).decode())
        prompt = ("Segment hazard zones relevant to this crisis: " + crisis
                  + ". Name each match: hull breach, radiation plume, "
                  "flood, or fire.")
        resp = httpx.post(
            SAM_BASE_URL.rstrip("/") + "/v1/responses",
            headers={"Authorization": f"Bearer {SAM_API_KEY}"},
            json={"model": "sam-3.1",
                  "input": [{"role": "user",
                             "content": [
                                 {"type": "input_text", "text": prompt},
                                 {"type": "image_url",
                                  "image_url": data_url}]}]},
            timeout=120.0,
        )
        resp.raise_for_status()
        return {"zones": [], "zones_raw": resp.text[:4000],
                "live_model": True, "source": image_path,
                "model": "sam-3.1",
                "note": "geometry arrives as special-token text; full mask "
                        "decoding follows the reading-segmentation guide"}
    if image_path:
        with open(image_path) as fh:
            zones = json.load(fh)["zones"]
        for z in zones:
            z.setdefault("bbox", _bbox(z["polygon"]))
        return {"zones": zones, "live_model": False,
                "source": image_path, "note": "operator-supplied mask"}
    if OPEN_BASE_URL and OPEN_API_KEY:
        data = _chat_json(
            "Emit JSON only: {\"zones\": [{\"id\": \"<slug>\", "
            "\"type\": \"hull_breach|radiation_plume|flood|fire\", "
            "\"polygon\": [[x, y], ...]}]}. Two zones, 0-100 coordinate "
            "space, polygons near the affected colony sector.",
            f"Map damage zones for this Mars colony crisis: {crisis}")
        zones = data.get("zones", [])
        for z in zones:
            z.setdefault("bbox", _bbox(z["polygon"]))
        return {"zones": zones, "live_model": True,
                "model": OPEN_MODEL, "note": "model-generated zones"}
    if offline():
        with open(os.path.join(DATA_DIR, "breach_mask.json")) as fh:
            zones = json.load(fh)["zones"]
        for z in zones:
            z.setdefault("bbox", _bbox(z["polygon"]))
        return {"zones": zones, "live_model": False,
                "note": "rehearsal fixture"}
    raise RuntimeError(
        "no damage source: provide an image/mask path, set "
        "OPEN_BASE_URL + OPEN_API_KEY, or COUNCIL_OFFLINE=1")


def route_zones(zones: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
    return {"logistics": list(zones),
            "medical": [z for z in zones
                        if z.get("type") in ("radiation_plume",
                                             "hull_breach", "fire")]}


def ingest_all(scenario_title: str, crisis: str,
               audio_path: str | None = None,
               image_path: str | None = None) -> Dict[str, Any]:
    telemetry = transcribe_dispatch_log(audio_path, crisis)
    damage = segment_damage(image_path, crisis)
    damage["routed"] = route_zones(damage.get("zones", []))
    return {"scenario": scenario_title, "telemetry": telemetry,
            "damage": damage}
