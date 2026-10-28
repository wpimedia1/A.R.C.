# MARS COUNCIL — Multi-Agent Council Dashboard

Event-driven multi-agent council with a live dashboard. Agents deliberate in
three rounds, steer to consensus, and preserve minority dissent.

## Hackathon compliance

- Models: Meta-only. Every agent reasons through the Meta Model API
  (`muse-spark-1.3`, OpenAI-compatible `/chat/completions`). Set
  `OPEN_BASE_URL` plus `OPEN_API_KEY`. Without keys the deterministic
  offline fallback runs so the demo never breaks.
- Track: Push the Frontier. Domain scenario is a Mars Industrial Colony
  Management simulator across the five pillars (Power Grid, Water
  Authority, Medical Center, Logistics & Mining, Manufacturing &
  Agriculture). Trigger engine: single agent by default, standalone
  Devil's Advocate check on partial ambiguity, full 7-agent council only
  on genuine ambiguity plus uncertainty plus irreversibility. Round 1
  runs in isolated workers (zero cross-influence by construction).
- Bonuses aimed at: Best Build on Meta Open Weight Models, Best Agentic
  Use-Case.
- New work, built during the event. Nothing here is a chatbot, a basic RAG
  app, or medical advice. The Medical Center is a simulated facility, not a
  diagnostic tool.

## Run (judges: double-click `start.bat`, `stop.bat` to quit)

One server, one address: `http://localhost:8000/`. The dashboard ships
prebuilt (`frontend/out`) and is served by the API itself, so judging time
needs no Node, no second port, no typing. `start.bat` checks Python,
creates the venv, installs requirements, waits for health, and opens the
browser. Pause, Resume, and Stop live on the dashboard itself. Rebuilding
the dashboard after frontend edits is the only step that needs Node:
`cd frontend && npm install && npm run build`.

Manual run (backend):

```
cd "Meta Global AI Developer Hackathon/council-dashboard/backend"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Env vars:

- `OPEN_BASE_URL` (default `https://api.meta.ai/v1`), `OPEN_API_KEY`,
  `OPEN_MODEL` (default `muse-spark-1.3`): Round 1 experts on the Meta
  Model API. `MODEL_BASE_URL` / `MODEL_API_KEY` work as fallback names.
- `SMART_BASE_URL`, `SMART_API_KEY`,
  `SMART_MODEL` (default `muse-spark-1.3`): Strategist and Devil's
  Advocate anchors on the Meta Model API (OpenAI-compatible
  `/chat/completions`). Blank `SMART_*` values inherit `OPEN_*`.
- Voice (`muse-voice-transcribe-1.0`, `POST /v1/asr/transcribe`,
  WAV only), SAM 3.1 (`POST /v1/responses`), Image (`muse-image-1.0`,
  `/v1/images/generations`): default to the Meta host and reuse your chat
  key unless overridden. Verified against dev.meta.ai docs.
- `IMAGE_BASE_URL`, `IMAGE_API_KEY`, `IMAGE_MODEL` (default `muse-image-1.0`):
  situation maps (else a labeled local SVG render of the real zones).
- `REDIS_URL` (optional): bridges every event to Redis PubSub.
- `COUNCIL_SEED` (default `7`), `UNCERTAINTY_THRESHOLD` (`0.35`),
  `CONSENSUS_THRESHOLD` (`0.9`).
- `COUNCIL_OFFLINE=1`: rehearsal mode. Seeded deterministic fallbacks and
  bundled fixtures, every payload labeled. Default is live: missing
  credentials raise a 502 with remediation, never silent mock data.

Endpoints: `GET /health`, `POST /run`
(body: `{"scenario": "reactor-failure", "audio_path": ..., "image_path": ...}`),
`GET /map`, `WS /ws` (live typed events).

Tests: `python -m unittest discover -s tests` from `backend/` (needs
`pip install -r requirements.txt`, torch included). Covers fuzzy math,
Hamacher bounds, K-Means/silhouette, DDPG reward and updates, fixture
parsing in rehearsal mode, and full-run determinism plus the complete
event contract.

Frontend development only: `cd frontend && npm install && npm run dev`
(open `http://localhost:3000` with the backend on `:8000`, or set
`NEXT_PUBLIC_API`). Production judging uses the prebuilt `frontend/out`
served from `http://localhost:8000/`.

## Demo replay

`POST /run {"scenario": "reactor-failure", "replay": true}` runs the 3-minute
simulated crisis: Round 1 isolation, Round 2 trust-network clustering,
Round 3 DDPG steering to the 0.9 threshold, then the consensus plan plus the
dissent log. The frontend replay button calls this.

## Layout

- `backend/app/events.py` — typed events, asyncio.Queue bus + Redis bridge.
- `backend/app/fuzzy.py` — hesitant fuzzy scoring, hesitation degrees.
- `backend/app/trust.py` — preference similarity, trust topology, Hamacher
  fusion, K-Means with silhouette.
- `backend/app/ddpg.py` — PyTorch actor-critic DDPG, online updates, seeded.
  Reward is exactly the spec formula: 0.5 consensus gain, minus 0.3 round
  penalty, plus 0.2 opinion retention.
- `backend/app/wonder.py` — Muse Wonder multi-path predictions above the
  uncertainty bar (live only; never invented).
- `backend/app/agents.py` — tiered model client (open weights / Muse Spark),
  Strategist, Devil's Advocate, domain experts.
- `backend/app/ingest.py` — Voice Transcribe + SAM 3.1 ingestion.
- `backend/app/tribe.py` — TRIBE v2 strain adapter.
- `backend/app/tools.py` — autonomous tool repair (synthesized diagnostics,
  really executed).
- `backend/app/maps.py` — Muse Image situation maps + labeled local renderer.
- `backend/app/mars.py` — colony simulator and crisis scenarios.
- `backend/app/council.py` — trigger engine and 3-round pipeline.
- `backend/app/main.py` — FastAPI app, websocket feed, map serving.
- `backend/tests/` — unittest contract suite.
- `frontend/` — Next.js + Zustand dashboard, D3 trust graph, replay button.
