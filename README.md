# A.R.C. — Autonomous Robotic Colony

**Autonomous Robotic Colony (A.R.C.)** is a Martian outpost simulation at Arcadia Planitia, run by Meta AI agents that reason over real Mars data: live DSN contacts, NASA weather history and HiRISE orbital imagery.

A persistent simulation in which a team of Meta-model agents plans and authorizes the robotic preparation of a site in Arcadia Planitia, Mars. Every physical quantity comes from a cited environment package; the simulator validates every proposal before it executes; every model request is recorded with the provider's `response_id` so it can be matched in the Meta developer dashboard.

**Status: not yet an accepted release.** Open items are listed in [docs/UNFINISHED-FEATURES.md](docs/UNFINISHED-FEATURES.md). Decisions, source conflicts and limits are in [docs/DECISIONS.md](docs/DECISIONS.md).

## What runs

| Part | Where | What it does |
|---|---|---|
| Environment package | `council-dashboard/backend/mission/packages/arcadia-mars-v1.json`, `mission/package.py` | 65 parameters from 24 sources, each published (source, page, quote), derived (formula, recomputed at load) or computed (IAPWS water density). Only parameters the simulation uses are kept. Refuses to load anything incomplete; the mission refuses to start while any operator decision is unapproved. |
| Simulator | `mission/engine.py`, `mission/spec.py` | Fission power deployment → survey → habitat trench → regolith shielding, and Rodwell drilling → water production. Rates, power, targets and costs come only from the package. Power allocation, equipment availability and dependencies are enforced. |
| Meta agents | `mission/planner.py`, `mission/agents.py`, `mission/provider.py` | Autonomous and onboard (D10). Independent assessments of one frozen observation (muse-spark-1.3), director reconciliation (muse-wonder-1.0), specialist tool loops in which every turn is self-contained (it carries the tool results so far; no `previous_response_id`), onboard assurance review. The director recharges excavator batteries from the fission grid (D18). Agents replan on job completion, faults, low batteries, work falling behind its authorized rate, new weather data, conjunction, season change and resume. Tools: inspect state/parameters/site evidence, estimate, submit work order, request replanning. No offline or fallback mode. |
| Meta media | `mission/media.py` | **SAM 3.1** segments boulders and impact craters at genesis in a 512 m full-resolution (0.5 m/pixel) window of HiRISE ESP_056974_2205 centred on the mission site; the detections route the survey around hazards (D13). Every call is recorded with HTTP status, x-request-id and cost. |
| Live Mars conditions | `mission/conditions.py`, `mission/worker.py` | Real Mars date, season and local time (Mars24), Earth–Mars distance, light time and solar conjunction (ERFA), and NASA DSN Now antenna activity read every minute, **including while the mission is paused**. The public mission runs in real Mars time. The agents run onboard (D10): live conditions inform them, but work never waits for Earth. |
| Records | `mission/store.py`, `mission/inspection.py` | Append-only revisions, inference receipts (response_id, x-request-id, key fingerprint, usage, cost), decision trail with input snapshot and calculation, export. |
| Evidence ingestion | `mission/science.py`, `terrain.py`, `telemetry.py`, `evidence.py` | USGS MOLA, SWIM ice and radar, Curiosity REMS and daily weather, NASA architecture documents. Off-site observations are never presented as Arcadia measurements. |
| Interface | `council-dashboard/frontend` | Today (live 3D outpost), Mars now, Outpost (equipment specifications), Work, Agents, Evidence, Records. Reads only persisted state. |

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

Set `MISSION_OPERATOR_TOKEN=<a secret you choose>` in `.env` in the repository root (git-ignored): only a Start request carrying it creates the mission. The app waits for the operator to press Start with that token; that creates the mission once (revision 1, the genesis record) in the `mission-db` volume; every later change is an appended revision. Without a key the worker stops planning and the interface shows the reason. To run without model calls, start with `MISSION_MODEL_MODE=fixed-priority docker compose up --build -d database api worker`: the interface labels it a fixed-priority benchmark. A mission recorded under another package or engine version came from a build that is no longer the tool: it is discarded on startup and Start begins a new genesis. Model receipts and spend stay in the append-only event log.

Tests in Docker: `docker compose --profile test run --rm tests`.

## Deploy (any cloud host with Docker)

Needs a server with Docker Compose, a domain name pointing at it, and ports 80 and 443 open. HTTPS is automatic (Caddy, Let's Encrypt).

```
git clone <this repository> && cd <repository>
cp deploy/env.example .env        # fill in DOMAIN, POSTGRES_PASSWORD, MODEL_API_KEY, MISSION_OPERATOR_TOKEN; .env is git-ignored
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```

- **Genesis** happens when the operator presses Start in the app (with `MISSION_OPERATOR_TOKEN`), not when the containers start: the mission record begins at that moment and is append-only from then on. Visitors cannot start it.
- **Upgrades** that change the package or engine: A mission recorded under another package or engine version came from a build that is no longer the tool: it is discarded on startup and Start begins a new genesis. Model receipts and spend stay in the append-only event log.
- Missing `DOMAIN`, `POSTGRES_PASSWORD`, `MODEL_API_KEY` or `MISSION_OPERATOR_TOKEN` stops the start with a message naming it. The API port is not exposed; only the HTTPS proxy is.
- **Spending:** visitor experiments are limited to $0 of model calls by default (`MISSION_VISITOR_*_LIMIT_USD`); cap the public mission with `MISSION_PUBLIC_DAILY_LIMIT_USD` / `MISSION_PUBLIC_MONTHLY_LIMIT_USD`.
- **Prebuilt image:** every push to `master`/`main` runs the test suite in Docker and publishes `ghcr.io/<owner>/<repo>:latest` (GitHub Actions, `.github/workflows/ci.yml`) for platforms that run images (API: default command; worker: `python -m mission.worker`; both need `DATABASE_URL` to PostgreSQL, worker needs `MODEL_API_KEY`).

## Versions

- `master`: autonomous. The agents run onboard and keep the outpost online themselves (D10, D18).
- `remote-operations` (tag `remote-final`): the last remote-operations version, in which every agent order waited for a real DSN uplink to Mars, the light time and an MRO relay pass.

## Start

The deployed app waits: nothing runs and no model is called until the operator presses **Start mission** with the operator token. That press is genesis (`POST /api/v1/start` with header `X-Operator-Token`, once; pressing again changes nothing, decision D17). The mission then runs in real Mars time.

## Verify

From `council-dashboard/backend`:

- `python -m pytest tests -q` — package validation, engine physics bookkeeping, tool validation, API permissions, planning failure paths. No mocked model transport.
- `python -m mission.package` — prints every parameter with its origin and any unapproved decision.
- `python -m mission.verify_sources` — checks every published quote verbatim against the PDFs in `sources/`; writes `docs/source-verification.json`.
- `python -m mission.cli benchmark` — deterministic fixed-priority baseline runs.

From the repository root:

- `python tools/verify_agent_loop.py` — two real planning cycles in an isolated database; writes every `response_id` to `docs/live-agent-loop.json`.

A report counts as evidence only after its `response_id`s are matched in the Meta developer dashboard.

## Built on

MetroDesk (the author's earlier work) and the pre-existing Mars Council scaffold (commit `44bd845`) are prior work. See [docs/CONTRIBUTIONS.md](docs/CONTRIBUTIONS.md).
