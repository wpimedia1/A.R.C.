# A.R.C. — Autonomous Robotic Colony

**Autonomous Robotic Colony (A.R.C.)** is a Martian outpost simulation at Arcadia Planitia, run by Meta AI agents that reason over real Mars data: live DSN contacts, NASA weather history and HiRISE orbital imagery.

A persistent simulation in which a team of Meta-model agents plans and authorizes the robotic preparation of a site in Arcadia Planitia, Mars. Every physical quantity comes from a cited environment package; the simulator validates every proposal before it executes; every model request is recorded with the provider's `response_id` so it can be matched in the Meta developer dashboard.

**Status: not yet an accepted release.** Open items are listed in [docs/UNFINISHED-FEATURES.md](docs/UNFINISHED-FEATURES.md). Decisions, source conflicts and limits are in [docs/DECISIONS.md](docs/DECISIONS.md).

## What runs

| Part | Where | What it does |
|---|---|---|
| Environment package | `council-dashboard/backend/mission/packages/arcadia-mars-v1.json`, `mission/package.py` | 55 parameters from 15 sources, each published (source, page, quote), derived (formula, recomputed at load) or computed (IAPWS ice/water properties). Refuses to load anything incomplete. Mission refuses to start while any operator decision is unapproved. |
| Simulator | `mission/engine.py`, `mission/spec.py` | Fission power deployment → survey → habitat trench → regolith shielding, and Rodwell drilling → water production. Rates, power, targets and costs come only from the package. Power allocation, equipment availability and dependencies are enforced. |
| Meta agents | `mission/planner.py`, `mission/agents.py`, `mission/provider.py` | Independent assessments of one frozen observation (muse-spark-1.3), director reconciliation (muse-wonder-1.0), specialist tool loops chained with `previous_response_id`. Tools: inspect state/parameters/site evidence, estimate, submit work order, request replanning. No offline or fallback mode. |
| Meta media | `mission/media.py` | **Muse Image** (muse-image-1.0) draws the site from the recorded mission state at genesis and after every completed job; each frame is an edit of the previous one, labeled AI illustration. **SAM 3.1** segments boulders and impact craters in a real HiRISE image of Arcadia Planitia (ESP_052358_2210, NASA/JPL-Caltech/UArizona) when the survey completes; detections are pinned as evidence the agents read. Every call is recorded with HTTP status, x-request-id and cost. |
| Live Mars conditions | `mission/conditions.py`, `mission/worker.py` | Real Mars date, season and local time (Mars24), Earth–Mars distance, light time and solar conjunction (ERFA), and NASA DSN Now antenna activity read every minute, **including while the mission is paused**. The public mission runs in real Mars time; agent work orders are uplinked from Earth and wait for a real DSN uplink to Mars and the light-time delay (D10). Conjunction, season change and resuming after a pause trigger replanning (D11). Experiments freeze conditions at the fork. |
| Records | `mission/store.py`, `mission/inspection.py` | Append-only revisions, inference receipts (response_id, x-request-id, key fingerprint, usage, cost), decision trail with input snapshot and calculation, export. |
| Evidence ingestion | `mission/science.py`, `terrain.py`, `telemetry.py`, `evidence.py` | USGS MOLA, SWIM ice and radar, Curiosity REMS and daily weather, NASA architecture documents. Off-site observations are never presented as Arcadia measurements. |
| Interface | `council-dashboard/frontend` | Today, Outpost (3D layout), Work, Agents, Evidence, Records. Reads only persisted state. |

## Run locally (Windows)

1. `council-dashboard\backend\.env` must contain `MODEL_API_KEY=` with your Meta Model API key.
2. Build the interface once: `cd council-dashboard\frontend && npm ci && npm run build`.
3. Double-click `council-dashboard\start.bat`. It validates the package, starts the API and worker, and opens http://127.0.0.1:8000/. `stop.bat` stops both.

If any input is missing the launcher stops and says which one. The API answers 503 with the reason if the mission cannot initialize.

## Run with Docker

Requires Docker with Compose. From the repository root:

1. Put `MODEL_API_KEY=<your Meta Model API key>` in `council-dashboard/backend/.env`. The worker reads only this file; the key never enters the image.
2. `docker compose up --build -d database api worker`
3. Open http://localhost:8020/.

The app waits for a user to press Start; that creates the mission once (revision 1, the genesis record) in the `mission-db` volume; every later change is an appended revision. Without a key the worker stops planning and the interface shows the reason. To run without model calls, start with `MISSION_MODEL_MODE=fixed-priority docker compose up --build -d database api worker`: the interface labels it a fixed-priority benchmark. `docker compose down -v` deletes the mission database.

Tests in Docker: `docker compose --profile test run --rm tests`.

## Deploy (any cloud host with Docker)

Needs a server with Docker Compose, a domain name pointing at it, and ports 80 and 443 open. HTTPS is automatic (Caddy, Let's Encrypt).

```
git clone <this repository> && cd <repository>
cp deploy/env.example .env        # fill in DOMAIN, POSTGRES_PASSWORD, MODEL_API_KEY; .env is git-ignored
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```

- **Genesis** happens when a user presses Start in the app, not when the containers start: the mission record begins at that moment and is append-only from then on.
- **Start over from a new genesis:** `docker compose -f compose.yaml -f compose.prod.yaml down -v` (permanently deletes the mission record), then `up` again.
- Missing `DOMAIN`, `POSTGRES_PASSWORD` or `MODEL_API_KEY` stops the start with a message naming it. The API port is not exposed; only the HTTPS proxy is.
- **Spending:** visitor experiments are limited to $0 of model calls by default (`MISSION_VISITOR_*_LIMIT_USD`); cap the public mission with `MISSION_PUBLIC_DAILY_LIMIT_USD` / `MISSION_PUBLIC_MONTHLY_LIMIT_USD`.
- **Prebuilt image:** every push to `master`/`main` runs the test suite in Docker and publishes `ghcr.io/<owner>/<repo>:latest` (GitHub Actions, `.github/workflows/ci.yml`) for platforms that run images (API: default command; worker: `python -m mission.worker`; both need `DATABASE_URL` to PostgreSQL, worker needs `MODEL_API_KEY`).
- `render.yaml` is a Render Blueprint draft for the same two services plus PostgreSQL.

## Start and landing

The deployed app waits: nothing runs and no model is called until a user presses **Start mission**. That press is genesis (`POST /api/v1/start`, once; pressing again changes nothing). The landing at the mission site then plays as a replay of NASA's published Mars 2020 entry, descent and landing timeline (entry at 20,000 km/h, parachute at 240 s / 11 km / 1,512 km/h, heat shield +20 s, backshell at 2,100 m, skycrane 12 s before touchdown at 20 m, touchdown at about 7 minutes), with Play, Pause and Stop. Values are shown as published at each event and labelled interpolated in between; unpublished values stay unknown; the heat-shield timing conflict in NASA's own captions is shown (decision D17). Then the live outpost runs in real Mars time.

## Verify

From `council-dashboard/backend`:

- `python -m pytest tests -q` — package validation, engine physics bookkeeping, tool validation, API permissions, planning failure paths. No mocked model transport.
- `python -m mission.package` — prints every parameter with its origin, the tracked conflicts and any unapproved decision.
- `python -m mission.verify_sources` — checks every published quote verbatim against the PDFs in `sources/`; writes `docs/source-verification.json`.
- `python -m mission.live_check` — four real Meta requests (both models, tool call + chained follow-up); prints each `response_id`.
- `python -m mission.cli benchmark` — deterministic fixed-priority baseline runs.

From the repository root:

- `python tools/verify_agent_loop.py` — two real planning cycles in an isolated database; writes every `response_id` to `docs/live-agent-loop.json`.

A report counts as evidence only after its `response_id`s are matched in the Meta developer dashboard.

## Built on

MetroDesk (the author's earlier work) and the pre-existing Mars Council scaffold (commit `44bd845`) are prior work. See [docs/CONTRIBUTIONS.md](docs/CONTRIBUTIONS.md).
