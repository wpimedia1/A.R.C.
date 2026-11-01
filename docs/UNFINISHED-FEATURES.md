# Gap register — October 31, 2026 (owner list 1–32)

Status: **Implemented** (built and run here) · **Unverified** (built; the live external service has not yet been exercised; run the named tool on the owner's machine) · **Missing** · **Blocked** (needs the named external input).

Whole-app run: `tools/verify_stack_run.py` starts the real API and worker processes and drives the public mission. Fixed-priority, 40 ticks: mission advanced to tick 40, power deployment and survey progressed, survey completed, costs accrued, 88 append-only history rows, interface served (`docs/stack-run-fixed-priority.json`). Meta mode without a key: planning stops with the explicit reason, mission keeps ticking, nothing held (`docs/stack-run-meta-no-key.json`). Live services cannot be reached from the build workspace: `tools/verify_live_integrations.py` checks DSN Now, the USGS footprint index, HiRISE, Muse Image and SAM 3.1 on the owner's machine and writes `docs/live-integrations.json`.

| # | Item | Status | Evidence | Next |
|---|---|---|---|---|
| 1 | DSN reading held every work order | Implemented | Parser reads ranges or round-trip light time from any nested target, records feed shape; a feed with dishes but no readable target raises (reason + first dish XML logged) | Owner: `verify_live_integrations.py`, compare `docs/dsn-sample.xml` with NASA DSN Now |
| 2 | Unverified reading must never block | Implemented | DSN may hold an order only when a spacecraft has matched the Mars distance in the last 24 h; otherwise `unconfirmed`/`unavailable`, flagged as an open condition, never held. Stack run: `held: []` | — |
| 3 | Fixes in the owner repo | Implemented | Delivered with this update | — |
| 4 | One append-only event log from genesis | Implemented | `event_log` table: every service-status write and every receipt change appended (SQLAlchemy before_flush), worker starts and errors (repeats counted); `/api/v1/missions/{id}/log` merges revisions + events | — |
| 5 | Overwritten status rows | Implemented | Status rows remain as "latest" caches; every write is also appended to `event_log` | — |
| 6 | DSN readings kept only on change | Implemented | Every reading appended to `environment_observations` (`dsn-reading` / `dsn-unavailable`) | — |
| 7 | Records/export show full history | Implemented | Records tab "Complete history from genesis" (filterable); export adds `event_log` and `environment_observations` | — |
| 8 | DSN Now live | Implemented | Owner's live run 2026-10-31 22:44 UTC: 14 dishes, MRO and Mars Odyssey (M01O) identified, uplink to Mars active (`docs/live-integrations.json`) | — |
| 9 | Muse Image stamped illustration live | Implemented | Owner's live run 2026-10-31: HTTP 200, x-request-id 512405fc-78cb-44fd-81a3-48b4c4320102, image stored and stamped. Two earlier runs were billed but lost to my receipt bugs (fixed) | — |
| 10 | SAM 3.1 output parsing | Implemented | Owner's live run: response resp_6ae66f6dd3c403fa9d61434d, status completed, one empty output_text lane = zero matches for "boulder" (valid per the SAM 3 protocol). The browse image is too coarse for metre-scale boulders | Run SAM on a full-resolution crop of the nearest site image |
| 11 | USGS HiRISE footprint search | Implemented | Owner's live run: no footprint contains 40° N 190° E; 28 RED images within ~1°; nearest ESP_056974_2205, centre 14 km from the site, used and labelled as such | — |
| 12 | Assurance review with open conditions | Unverified | Enforced in engine; rejected approval without acknowledgements | First live planning cycle |
| 13 | Logistics agent replacement orders | Unverified | Engine + logistics tested; benchmark orders automatically | First live failure |
| 14 | Docker image + PostgreSQL drills | Unverified | Docker Hub unreachable here | `docker compose down -v && docker compose up --build -d database api worker` |
| 15 | HTTP 429 / timeouts | Implemented | 429 retried up to 3× honouring Retry-After (≤ 60 s; else 5/15/45 s), every attempt recorded; timeouts and 5xx never retried (may have been charged) | — |
| 16 | Random equipment failures | Implemented | D14: rover and excavators fail at 6.551e-4 /h (MTBF ≈ 1,526 h), series sum of module rates, Stancliff, Dolan & Trebi-Ollennu 2005 Table 2; deterministic per mission seed; failures stop work and trigger D12 replacement. Nominal forecast and benchmark exclude failures and say so | — |
| 17 | Robotic repair time | **Blocked** | No published repair procedure/time for these machines; failed units are replaced (D12) | Source a repair time |
| 18 | Orbiter relay pass timing | Implemented | D15: delivery at the next MRO node time over the site (15:03 LMST published, NTRS 20080012690; 03:03 descending) after the light time | Other relay orbiters not modeled |
| 19 | Cold limits; Arcadia temperatures | **Blocked** | Found only IPEx actuator thermal-cycle test temperatures (−35 °C to 40 °C mobility, JPL-provided), which are internal actuator limits, not ambient limits; no Arcadia temperature series | Mars Climate Database series + heated-actuator thermal model source |
| 20 | Radiation limits for electronics | **Blocked** | RAD gives biological dose equivalent only | Total-dose tolerance per machine |
| 21 | Habitat offload (D4) | **Blocked** | Offloading paper has no duration or power | Offload timeline source |
| 22 | Ice depth/purity across the site | **Blocked** | SWIM is a consistency index | Site-scale ice map |
| 23 | Rodwell mass/capital | **Blocked** | RedWater papers (Mank 2021 abstract) give no mass | Full-text mass |
| 24 | `iapws` GPL-3.0 | **Blocked** | Owner's license decision | — |
| 25 | Agents create work | Implemented | Package templates `water-batch`, `survey-extension`; director tool `create_job`; readiness criteria unchanged | — |
| 26 | Moon and Earth packages | Missing | `spec.py` builds the Mars mission from Mars parameters; a lunar mission needs its own sourced job set | Write `moon-south-pole-v1` package + spec |
| 27 | Correlated-error check | Implemented | `evaluation.py`, `/evaluation`, Agents tab: pairwise agreement, consensus outcomes, shared gaps, flags | — |
| 28 | Provenance tags in Records | Implemented | Parameter tables tagged Published/Computed | — |
| 29 | Accessibility | Implemented (automated) | axe-core 4.10: 0 serious/critical violations on all 7 views after fixing timeline contrast; visible focus outlines. Manual screen-reader review not done | Manual review |
| 30 | Today page overcrowded | Implemented | Today = hero, five-field status bar, "What just happened" feed, plan, results; About/legend and AI art collapsed; live Mars on its own "Mars now" tab | — |
| 31 | Web quotes vs archived copies | Implemented / Unverified | `tools/archive_sources.py` saves each web source to `sources/web/`; `verify_sources` checks quotes in those copies; archiving needs the owner's network (37 verified, 0 failed, 27 web-only unchecked here) | Owner run of the archive tool |
| 32 | Hosting, commit/push, demo video, genesis | Implemented / Blocked | Deploy files: `compose.prod.yaml` (HTTPS proxy, required secrets fail loud, API port closed, visitor spend $0 by default), `deploy/env.example`, CI builds and tests the image and publishes to GHCR on push. Not run here: Docker Hub is unreachable from this workspace, so the image build is first verified by CI on the first push. Push: waiting for the owner's empty public GitHub repository. Hosting, genesis and video: owner | Owner: create repo; deploy; genesis |
| 33 | User-started genesis and landing replay | Implemented | D17. API and worker only check the database; `POST /api/v1/start` creates the mission once. `GET /missions/{mid}/landing` (every value with parameter, quote and URL; unpublished values null). `LandingSequence.tsx`: Play / Pause / Stop, plays right after Start. Tests: `test_mission_waits_for_start`, `test_landing_is_fully_sourced`; `tools/verify_stack_run.py` (real API + worker): waits for Start, Start creates genesis, worker advances | — |
| 34 | 3D outpost scene (Today) | Implemented | `MissionScene.tsx`: robots move only while their job runs, waiting robots show order ETA, order packets Earth → MRO → asset, real sun direction, HiRISE ground, replay from genesis | — |
| 35 | Running visibility, no invented values | Implemented | `LiveStrip.tsx`: RUNNING / NOT ADVANCING from the worker heartbeat, ticking Earth UTC and site time, next-step countdown, DSN uplink status. Unknown values show as unknown or waiting (order arrival, sun, step times, costs, power, DSN counts); no fallback numbers | — |


## Measured → estimated → checked (D16)

| Item | Status | Evidence | Next |
|---|---|---|---|
| Real Mars weather drives agent reasoning | Implemented / Unverified (live feed) | `mission/nowcast.py`. Run here on 4,745 sols of real Curiosity REMS history (NASA feed as cached by the public `marslog` repository, retrieved 2026-10-31): newest measurement sol 4995 (2026-08-25), 65 sols behind today; estimates for the gap and the next 3 sols; replaying the August release checked 21 earlier estimates, 21 confirmed, mean absolute error 2.1 °C (air min). Backtest over sols 3600–4900: 85–100 % of measurements inside the 95 % intervals at leads 1–90 sols. Worker reads the NASA feeds every 6 h; agents receive measurements, estimates and track record; the director can order standby citing them. Mars now tab shows all three | Owner run of `verify_live_integrations.py` (`nasa-weather` check) |
| Perseverance MEDA feed | Unverified | The public feed carried only 7 sols (April 2024) in the cached copy; handled, labelled | — |
| Dust opacity from the feed | Blocked | NASA's feed reports `atmo_opacity` as "Sunny" for 4,742 of 4,745 sols: not usable as a measurement | Orbiter dust-opacity product |
| Wind | Blocked | No current public wind feed (InSight ended 2022) | PDS InSight TWINS archive ingest for historical patterns |

## Done (with evidence)

- Live agent loop on the rebuilt engine (owner's machine, 2026-10-31, `docs/live-agent-loop.json`): two cycles, 15 provider requests, all HTTP 200 with `response_id`, $0.297. Each cycle's assessments shared one frozen observation with peer proposals withheld; cycle 2 received 4 role-memory entries. Agents authorized power deployment (fsp-1) and the survey (rover-1), citing oleson2022, fsp2024 and autonav2021.
- Provider calls confirmed by the owner in the Meta developer dashboard (2026-10-31) for the 2026-10-30 `live_check` run.
- Source quotes: 36 of 48 published parameters verified verbatim against local PDFs (`python -m mission.verify_sources`).
- Meta Responses API integration: `live_check` on the owner's machine, 2026-10-30, four HTTP 200 responses with `response_id` and `x-request-id`, tool call plus `previous_response_id` follow-up on muse-spark-1.3 and muse-wonder-1.0.
- Environment package validator and IAPWS computations: `tests/test_package.py`.
- Package-driven engine, conservation and power/equipment enforcement: `tests/test_engine.py`; `python -m mission.cli benchmark` (baseline readiness at sol 81.5).
- Agent tool validation without network: `tests/test_tools.py`, `tests/test_planning.py`.
- Legacy offline/rehearsal council removed from the working tree; `start.bat` launches only the mission service and fails without `MODEL_API_KEY`.
- Interface rebuilt against the new state; static build and type check pass; headless browser run of all six views with no page errors (cloud workspace, fixed-priority mode).
