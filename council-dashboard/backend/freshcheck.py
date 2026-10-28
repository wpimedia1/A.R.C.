"""Launcher helper: exit 0 only if a CURRENT server answers on :8000.

A stale server from an older run can answer /health with tiers but still
lack SMART-tier inheritance. Require that capability explicitly.
Anything else (stale or nothing) exits nonzero so the launcher starts
fresh instead of talking to a ghost.
"""

import json
import sys
import urllib.request

try:
    body = json.load(urllib.request.urlopen(
        "http://localhost:8000/health", timeout=5))
except Exception:
    sys.exit(2)

current = (isinstance(body, dict) and "tiers" in body
           and body.get("smart_inherit") is True)
sys.exit(0 if current else 1)
