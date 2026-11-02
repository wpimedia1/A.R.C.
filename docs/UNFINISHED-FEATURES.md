# Gap register

Status: **Implemented** (built and run) · **Unverified** (built; the live external service has not been exercised on the current code) · **Missing** · **Blocked** (needs the named external input). Live results recorded on earlier code are not carried forward: re-run the named tool.

| # | Item | Status | Evidence | Next |
|---|---|---|---|---|
| 1 | DSN reading held every work order | Implemented | Parser reads ranges or round-trip light time from any nested target, records feed shape; a feed with dishes but no readable target raises (reason + first dish XML logged) | Owner: `verify_live_integrations.py`, compare `docs/dsn-sample.xml` with NASA DSN Now |
| 2 | Unverified reading must never block | Implemented | DSN may hold an order only when a spacecraft has matched the Mars distance in the last 24 h; otherwise `unconfirmed`/`unavailable`, flagged as an open condition, never held. Stack run: `held: []` | — |
| 4 | One append-only event log from genesis | Implemented | `event_log` table: every service-status write and every receipt change appended (SQLAlchemy before_flush), worker starts and errors (repeats counted); `/api/v1/missions/{id}/log` merges revisions + events | — |
| 6 | DSN readings kept only on change | Implemented | Every reading appended to `environment_observations` (`dsn-reading` / `dsn-unavailable`) | — |
| 7 | Records/export show full history | Implemented | Records tab "Complete history from genesis" (filterable); export adds `event_log` and `environment_observations` | — |
| 8 | DSN Now live | Implemented | Owner's machine, current code, 2026-11-02 01:16 UTC: 14 dishes read every minute; Mars Odyssey (M01O) identified by its DSN code; live uplink Madrid DSS53 → M01O detected and recorded | — |
| 9 | Muse Image stamped illustration live | Implemented | Owner's live run 2026-10-31: HTTP 200, x-request-id 512405fc-78cb-44fd-81a3-48b4c4320102, image stored and stamped. Two earlier runs were billed but lost to my receipt bugs (fixed) | — |
| 10 | SAM 3.1 output parsing | Implemented | Owner's machine, current code: SAM 3.1 completed on the full-resolution site window; an empty output lane is parsed as zero matches (SAM 3 protocol) | — |
| 11 | HiRISE imagery and SAM at the site | Implemented | Owner's machine, current code, 2026-11-02 01:26 UTC: site = centre pixel of ESP_056974_2205 (D13); full-resolution JPEG2000 downloaded, 1,024 × 1,024 px (512 m) window decoded, SAM 3.1 accepted it as an embedded image; 0 boulders and 0 impact craters at 0.5 m/pixel; A* route found, detour ×1.0; pinned as hirise-site:938c8c6d8b84b81c. First attempt failed (missing `packaging` module), fixed and re-run with `mission.cli retry-site-analysis` | — |
| 12 | Assurance review with open conditions | Implemented | Owner's machine, current code: assurance approved power and survey only after acknowledging the open conditions (no uplink window yet) | — |
| 13 | Logistics agent replacement orders | Unverified | Engine + logistics tested; benchmark orders automatically | First live failure |
| 14 | Docker image + PostgreSQL drills | Implemented / Unverified | Docker image builds and runs on the owner's machine and in GitHub Actions (tests pass in the image). PostgreSQL backup drill not run on current code | `python tools/verify_postgres.py` |
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
| 29 | Accessibility | Unverified | The earlier axe-core pass was on an older interface | Re-run axe-core on all 7 views |
| 31 | Web quotes vs archived copies | Implemented / Unverified | `tools/archive_sources.py` saves each web source to `sources/web/`; `verify_sources` checks quotes in those copies; archiving needs the owner's network (37 verified, 0 failed, 27 web-only unchecked here) | Owner run of the archive tool |
| 32 | Hosting, commit/push, demo video, genesis | Implemented / Blocked | Deploy files: `compose.prod.yaml` (HTTPS proxy, required secrets fail loud, API port closed, visitor spend $0 by default), `deploy/env.example`, CI builds and tests the image and publishes to GHCR on push. Not run here: Docker Hub is unreachable from this workspace, so the image build is first verified by CI on the first push. Push: waiting for the owner's empty public GitHub repository. Hosting, genesis and video: owner | Owner: create repo; deploy; genesis |
| 33 | User-started genesis | Implemented | D17. API and worker only check the database; `POST /api/v1/start` creates the mission once. Tests: `test_mission_waits_for_start`; `tools/verify_stack_run.py` (real API + worker): waits for Start, Start creates genesis, worker advances | — |
| 34 | 3D outpost scene (Today) | Implemented | `MissionScene.tsx`: robots move only while their job runs; rover position = metres driven in the simulation along its survey line; trench and dome sizes from the package; order packets drawn only once sent; real sun direction; HiRISE ground; replay from genesis. Removed: landing replay, decorative MRO orbiter | — |
| 35 | Running visibility, no invented values | Implemented | `LiveStrip.tsx`: RUNNING / NOT ADVANCING from the worker heartbeat, ticking Earth UTC and site time, next-step countdown, DSN uplink status. Unknown values show as unknown or waiting (order arrival, sun, step times, costs, power, DSN counts); no fallback numbers | — |

## Measured → estimated → checked (D16)

| Item | Status | Evidence | Next |
|---|---|---|---|
| Real Mars weather drives agent reasoning | Implemented | `mission/nowcast.py`. Run here on 4,745 sols of real Curiosity REMS history (NASA feed as cached by the public `marslog` repository, retrieved 2026-10-31): newest measurement sol 4995 (2026-08-25), 65 sols behind today; estimates for the gap and the next 3 sols; replaying the August release checked 21 earlier estimates, 21 confirmed, mean absolute error 2.1 °C (air min). Backtest over sols 3600–4900: 85–100 % of measurements inside the 95 % intervals at leads 1–90 sols. Worker reads the NASA feeds every 6 h; agents receive measurements, estimates and track record; the director can order standby citing them. Mars now tab shows all three | Owner run of `verify_live_integrations.py` (`nasa-weather` check) |
| Perseverance MEDA feed | Implemented (limited data) | Owner's machine, current code, 2026-11-02: the live NASA feed returns 7 sols (MSL feed: 4,745 sols; 345 estimates made); handled and labelled | — |
| Dust opacity from the feed | Blocked | NASA's feed reports `atmo_opacity` as "Sunny" for 4,742 of 4,745 sols: not usable as a measurement | Orbiter dust-opacity product |
| Wind | Blocked | No current public wind feed (InSight ended 2022) | PDS InSight TWINS archive ingest for historical patterns |

## Checks to re-run on the current code (owner's machine)

- `python tools/verify_live_integrations.py`: NASA weather, DSN Now, USGS footprints, HiRISE, Muse Image, SAM 3.1.
- `python tools/verify_agent_loop.py`: two real planning cycles in an isolated database.
- `python tools/archive_sources.py && python -m mission.verify_sources`: archive web sources and check every quote.
