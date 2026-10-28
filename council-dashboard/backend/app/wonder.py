"""Muse Wonder multi-path scenario predictions.

During high-uncertainty evaluations the council asks Wonder for alternate
future paths. Live endpoint only: without WONDER_BASE_URL + WONDER_API_KEY
no paths are produced at all. Future paths are never heuristically
invented; an unconfigured call returns empty with an honest note.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import httpx

WONDER_BASE_URL = os.environ.get("WONDER_BASE_URL",
                                       "https://api.meta.ai/v1")
WONDER_MODEL = os.environ.get("WONDER_MODEL", "muse-wonder-1.0")


def _wonder_key() -> str:
    for name in ("WONDER_API_KEY", "OPEN_API_KEY", "SMART_API_KEY",
                 "MODEL_API_KEY"):
        val = os.environ.get(name, "")
        if val:
            return val
    return ""


WONDER_API_KEY = _wonder_key()

UNCERTAINTY_BAR = 0.6


def predict_paths(crisis: str, options: List[str],
                  uncertainty: float) -> Dict[str, Any]:
    if not (WONDER_BASE_URL and WONDER_API_KEY):
        return {"paths": [], "wonder_live": False,
                "note": "WONDER unconfigured; no paths predicted"}
    resp = httpx.post(
        WONDER_BASE_URL.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {WONDER_API_KEY}"},
        json={
            "model": WONDER_MODEL,
            "messages": [
                {"role": "system", "content":
                 "Emit JSON only: {\"paths\": [{\"title\": \"<name>\", "
                 "\"likelihood\": 0.0-1.0, "
                 "\"fallout\": \"<one sentence>\"}]}. Three paths."},
                {"role": "user", "content":
                 f"Crisis: {crisis}\nOptions: {', '.join(options)}\n"
                 f"Current uncertainty: {uncertainty:.2f}. Predict three "
                 f"distinct future paths if deliberation stalls."},
            ],
            "temperature": 0.7,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    data = json.loads(resp.json()["choices"][0]["message"]["content"])
    paths = data.get("paths", [])[:3]
    return {"paths": paths, "wonder_live": True, "model": WONDER_MODEL}
