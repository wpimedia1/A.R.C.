"""Situation maps: Muse Image generation with a labeled local renderer.

On Round 3 consensus the dashboard needs a high-contrast hazard overlay
and evacuation-route map. With IMAGE_BASE_URL set, Muse Image renders it.
Otherwise a local SVG renderer draws zones, routes, and the chosen action
from the same inputs, and the payload says so.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

IMAGE_BASE_URL = os.environ.get("IMAGE_BASE_URL", "https://api.meta.ai")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "muse-image-1.0")


def _image_key() -> str:
    for name in ("IMAGE_API_KEY", "OPEN_API_KEY", "SMART_API_KEY",
                 "MODEL_API_KEY"):
        val = os.environ.get(name, "")
        if val:
            return val
    return ""


IMAGE_API_KEY = _image_key()


def _svg_map(title: str, action: str, zones: List[Dict[str, Any]]) -> str:
    colors = {"hull_breach": "#ff4d5e", "radiation_plume": "#ffb020"}
    polys = []
    for z in zones:
        pts = " ".join(f"{x * 8},{y * 5}" for x, y in z.get("polygon", []))
        c = colors.get(z.get("type", ""), "#4da3ff")
        polys.append(
            f'<polygon points="{pts}" fill="{c}" fill-opacity="0.35" '
            f'stroke="{c}" stroke-width="2"/>'
            f'<text x="{z["bbox"][0] * 8}" y="{z["bbox"][1] * 5 - 6}" '
            f'fill="{c}" font-size="13" font-family="monospace">'
            f'{z["id"]}</text>')
    route = ('<polyline points="20,470 160,380 320,380 470,250" fill="none" '
             'stroke="#2dd4a8" stroke-width="3" stroke-dasharray="8 5"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="560" height="500" '
        f'viewBox="0 0 560 500"><rect width="560" height="500" fill="#0b0f19"/>'
        f'<text x="16" y="28" fill="#e8edf5" font-size="16" '
        f'font-family="monospace">{title} :: {action}</text>'
        f'{"".join(polys)}{route}'
        f'<text x="16" y="484" fill="#2dd4a8" font-size="12" '
        f'font-family="monospace">- - evacuation route</text></svg>')


def generate_situation_map(title: str, action: str,
                           zones: List[Dict[str, Any]],
                           out_path: str) -> Dict[str, Any]:
    if IMAGE_BASE_URL and IMAGE_API_KEY:
        try:
            prompt = (f"High-contrast tactical situation map for Mars colony "
                      f"crisis '{title}'. Hazard overlays at {zones}. "
                      f"Evacuation route marked. Decided action: {action}.")
            resp = httpx.post(
                IMAGE_BASE_URL.rstrip("/") + "/images/generations",
                headers={"Authorization": f"Bearer {IMAGE_API_KEY}"},
                json={"model": IMAGE_MODEL, "prompt": prompt,
                      "size": "1024x1024"},
                timeout=120.0,
            )
            resp.raise_for_status()
            url = resp.json()["data"][0].get("url", "")
            return {"map": url, "live_model": True}
        except Exception as exc:
            note = f"live call failed ({exc}); local render"
        else:
            note = ""
    else:
        note = "local render"
    svg = _svg_map(title, action, zones)
    with open(out_path, "w") as fh:
        fh.write(svg)
    return {"map": out_path, "live_model": False, "note": note}
