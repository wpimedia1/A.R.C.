"""Diagnose the Meta Model API credential and nothing else.

Tests every credential source against every chat endpoint and prints
only HTTP statuses plus short body excerpts. Key values are never
printed, only prefix/suffix/length hints. Standard library only.
"""

import json
import os
import sys
import urllib.request

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_env(path):
    out = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError as exc:
        print(f"cannot read {path}: {exc}")
    return out


def hint(key):
    return f"{key[:3]}…{key[-2:]} (len {len(key)})" if key else "(empty)"


def post(url, key, payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()[:300]
    except Exception as exc:
        return f"FAILED ({exc})", ""


def main():
    file_env = load_env(BASE)
    base = file_env.get("OPEN_BASE_URL",
                        "https://api.meta.ai/v1").rstrip("/")
    model = file_env.get("OPEN_MODEL", "muse-spark-1.3")
    candidates = [(".env OPEN_API_KEY", file_env.get("OPEN_API_KEY", ""))]
    sys_key = os.environ.get("MODEL_API_KEY", "")
    if sys_key and sys_key != candidates[0][1]:
        candidates.append(("environ MODEL_API_KEY", sys_key))
    print(f"base: {base}")
    print(f"model: {model}")
    for label, key in candidates:
        print(f"--- {label}: {hint(key)}")
        if not key:
            print("    skipped (empty)")
            continue
        s, b = post(base + "/chat/completions", key,
                    {"model": model,
                     "messages": [{"role": "user",
                                   "content": "Reply with: ok"}]})
        print(f"    chat/completions -> {s} {b[:160]}")
        s, b = post(base + "/responses", key,
                    {"model": model, "input": "Reply with: ok",
                     "stream": False})
        print(f"    responses -> {s} {b[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
