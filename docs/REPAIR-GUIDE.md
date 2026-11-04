# Local repair and verification guide

This is a planning and execution simulator, with Mars as its first environment. It does not control robots or constitute a NASA colonization plan. The mission timeline is calculated from the configured jobs and reference operating points, not an actual NASA deployment schedule.

## What changed

- Unknown power can no longer authorize work. Drilling reserves a cited 15 kW RedWater whole-system design allocation, with that scope recorded in decisions.
- Water production consumes a finite feed allocation and respects finite storage. These initial allocations equal the configured mission objective; neither is claimed as a measured ice deposit or installed tank specification.
- Rover reference battery storage, mobility consumption and onboard generation are accounted separately from grid power. Excavators retain grid charging. Meta agents can authorize a standing charging policy; normal charge completion then continues without an unnecessary council. Changed constraints still request replanning.
- Component temperature and total-ionizing-dose envelopes accept unit-checked experiment inputs. Local internal sensors remain uninstrumented; climate temperature does not impersonate a battery sensor.
- One-tick standby now holds one complete interval. Delivered replacements get a fresh equipment generation rather than inheriting the failed unit's depleted battery or standby state.
- Director memory is retained. Newly created jobs can enter specialist loops without a missing-assessment exception. Equipment-blocked jobs reach specialists for explicit escalation; conflict review can authorize validated charging.
- Provider response identity and public tool output are recorded before argument parsing. Failed requests retain explicit error details. Authenticated GET retrieval matched 51 historical records to Meta response identity, model, usage and public tool calls. One response ID returned HTTP 404; three records had no retrievable response ID. These four remain unverified. This does not validate the repaired planner through new generation; see historical-response-check.json.
- Version mismatch preserves mission history. Explicit upgrade appends a revision and pauses; it never silently deletes the earlier mission.
- Real MCD 6.2 site climatology is downloaded, pinned, plotted and available to agent context/tools. NASA REMS history remains explicitly off-site observed data.
- Each scientific publisher refreshes independently. A failed source does not prevent subsequent products from refreshing. Image serving uses pinned evidence shared through PostgreSQL rather than the worker's private frontend filesystem.
- Private experiments expose priorities, equipment availability, water allocations, production derating and scenario operating expenditure controls.
- CLI Earth/Moon construction-study packages and matched fixed-scheduler seed/fault experiments are available. Their scope is limited; see the unfinished register.
- Stale DSN contact no longer says “uplink now.” Worker visibility uses its heartbeat. Paused/stale-worker scenes stop depicting execution. Failed terrain-image loads display an explicit message and do not generate substitute terrain. Ground rendering also rejects absent or proxy source pins; only site-covering pinned imagery can be used. Equipment labels use regular accessible DOM to avoid canvas-root cleanup failures on navigation.

## Models and responsibilities

[Meta’s current model documentation](https://dev.meta.ai/docs/models), checked November 3, confirms Wonder for long-horizon work and the configured Wonder/Spark IDs. An authenticated catalog GET returned HTTP 200 and listed Wonder, Spark and SAM; see model-catalog-check.json. This confirms catalog access, not inference execution or dashboard attribution.

| Configured model | Used for | Verification limit |
|---|---|---|
| `muse-wonder-1.0` | Mission director: reconcile independent assessments, sequence work and review conflicts | Engine 9 completed two real planning cycles, then continued to tick 146. All 67 responses matched Meta retrieval; the run was deliberately paused before readiness. Engine 10 completed two real cycles (17 matched responses across Wonder/Spark), including a source-cited standing charging authorization. Full nominal/fault acceptance is recorded separately. |
| `muse-spark-1.3` | Survey, construction, resources, power, logistics, assurance; bounded tool loops; memory consolidation, including director lessons | Actual specialist proposals/assurance and sol-boundary consolidation ran in isolated acceptance; inspect live-agent-loop.json and the current response-authentication report. Unit-test doubles remain separate. |
| SAM 3.1 | Segment actual HiRISE site imagery for orbital hazard analysis | Not called during this repair. No new segmentation run. The historical GET audit identifies which stored responses matched and which remain unverified. |
| No model | State transitions, reservations, accounting, readiness, planetary geometry, source parsing and explicit fixed-priority benchmark | These are deterministic software operations. |

Credentials are read server-side from `MODEL_API_KEY` in `council-dashboard/backend/.env`, otherwise the process environment. They are not included in frontend code or Docker images. Missing credentials stop Meta planning visibly. No scheduler silently replaces failed Meta planning.

## Data and what each can establish

- NASA architecture documents: extracted passages with pages, source hashes and interpretation. These establish architectural context, not equipment certification.
- USGS MOLA: observed regional elevation. Native spacing is approximately 463 m; sampled overviews are coarser. It cannot clear rover-scale obstacles.
- SWIM composite consistency and radar: published regional evidence for prospecting, not ice fraction or guaranteed recoverable reserves.
- HiRISE: actual ESP_056974_2205 site imagery independently retrieved and verified against PDS projected pixel bounds. Acquired 2018-09-21; credit NASA/JPL-Caltech/UArizona. This is image evidence, not a SAM run. Segmentation remains separate model output, not ground-truth hazard certification. Mission-specific rendering checks pinned image bytes and ownership.
- REMS/MEDA: published measurements at Gale/Jezero, with their observation age. Statistical nowcasts stay labeled estimates.
- MCD 6.2: site-specific climate model output, not live Arcadia measurement. A real retrieval in this repair returned 25 diurnal samples for each of air temperature, surface temperature and pressure at 40.05451° N, 190.28958° E, Ls 16°. Raw ASCII SHA-256: `6518c318cfd19360c697f9378a8b774d5bab221c3db0e654504c0312003356ea`.
- Mars24/ERFA: calculated date, sunlight and planetary geometry. NASA DSN Now: actual antenna activity with freshness checks. DSN observations do not establish that the hypothetical outpost communicated with Earth.

Full engineering citations and unresolved applicability are in [ENGINEERING-REFERENCES.md](ENGINEERING-REFERENCES.md). Raw source archives and large datasets remain outside Git. MCD attribution/use terms, NASA media credits, Kenney CC0 and library licenses remain applicable. Removing GPL IAPWS is not a complete license-clearance opinion.

## Setup and run without Docker

PowerShell, from the repository root:

- Install Python 3.10+ and Node.js 22, then create the environment if absent: `python -m venv council-dashboard/backend/.venv`.
- Install dependencies: `council-dashboard/backend/.venv/Scripts/python.exe -m pip install -r council-dashboard/backend/requirements-mission.txt`.
- Build the UI: change to `council-dashboard/frontend`, run `npm ci`, then `npm run build`.
- In a backend terminal, select a database with `$env:DATABASE_URL='sqlite:///local-review.db'` and start the API: `.venv/Scripts/python.exe -m uvicorn mission.api:app --host 127.0.0.1 --port 8000`.
- Open http://127.0.0.1:8000/. The API alone serves the UI and never dispatches planning calls. Genesis requires `MISSION_OPERATOR_TOKEN`; use a fresh database for an isolated experiment.
- For explicitly labeled fixed-priority operation, set `$env:MISSION_MODEL_MODE='fixed-priority'` in both API and worker terminals. Start `.venv/Scripts/python.exe -m mission.worker` only when you intend to advance that database. It retrieves public sources; it does not run Meta/SAM in fixed-priority mode.
- For actual agents, configure the Meta credential and use Meta mode. Starting the worker on an active Meta mission can dispatch planning and SAM requests. The real Wonder/Spark acceptance uses isolated databases; the original public worker remains stopped.
- `start.bat` is the agent-mode convenience launcher and requires the Meta credential. The manual commands above support API-only inspection and the explicitly selected benchmark.

## Optional Docker setup and run

- Build: `docker compose --profile test build api worker tests`.
- Start PostgreSQL and API: `docker compose up -d database api`. Normal app address: http://127.0.0.1:8020/.
- With an older mission package, the API intentionally reports a version mismatch. Back up and review the migration before running `docker compose run --rm api python -m mission.cli upgrade`. It preserves history and leaves the mission paused.
- Start `worker` and resume only when you intend to run the configured planner. Review work orders, source pins and credential provenance first.
- Run tests: `docker compose --profile test run --rm tests`. Database fixtures create separate schemas; they do not reset the public mission.
- The repair review is separate: http://127.0.0.1:8021/, container `meta-hackathon-review-api`, database `mission_review_20261103`. It is a paused restored copy with no worker or model credential. Starting Docker Desktop by itself does not recreate this disposable review container after removal.

## Inspect the work

- Today: objective, actual state, current blocker and work basis. Paused state must stay visible.
- Work: select a job, inspect its inputs, calculation and decision; keyboard Escape closes the drawer.
- Evidence: inspect a mapped orbital cell, a climate sample or an off-site measurement; follow its pinned source/version and source link.
- Agents: inspect stored request statuses, returned IDs, summaries, tool outcomes and usage. Use historical-response-check.json to distinguish the 51 provider-matched historical records from the four unverified records. A new cycle needs its own provider correlation.
- Create an experiment: change one priority or allocation, select the explicit benchmark if avoiding provider calls, then run a bounded experiment with a worker pointed to that review database. Public state must remain unchanged. This review instance deliberately has no worker running.
- Records: export the retained history and provenance. Migration adds a revision; it does not rewrite earlier results.

## Evidence and limits

- `source-verification.json`: 59 package quotations matched; zero unmatched/unchecked. Three unrelated PDF pages failed extraction and are explicitly recorded. This is text matching, not engineering validation.
- `postgres-recovery.json`: real backup/restore comparison of ten tables and 8,824 rows. The restored copy matched. The original database was not overwritten.
- `operations-benchmark.json`: twenty fixed-scheduler runs, five seeds across nominal/power loss/delayed excavation/equipment failure, 1,200 steps from the same commissioned-power snapshot. No instrumented power/battery/prerequisite violations. None reached readiness within this horizon; no superiority or full-mission completion claim is supported. Temporary equipment unavailability is restored after six steps in the delay case; automatic replacement logistics still applies under the benchmark policy.
- 147-test Windows and PostgreSQL regressions and browser results are recorded in STATUS.md and the local verification report. Planning unit tests contain injected responses, clearly separated from live provider testing.
- The original public mission was neither upgraded nor restarted. Authenticated GET retrieval matched 51 historical records to Meta response identity, model, usage and public tool calls. One response ID returned HTTP 404; three records had no retrievable response ID. These four remain unverified. This does not validate the repaired planner through new generation; see historical-response-check.json. After explicit owner authorization, 67 engine-9 Wonder/Spark responses were generated and independently matched through Meta GET retrieval. No publication, deployment or commits were performed.

All remaining implementation and verification gaps are listed in [UNFINISHED-FEATURES.md](UNFINISHED-FEATURES.md). This is not a claim that the entire original product specification is finished.

## Engine-9 follow-up implementation

Executable repair, serial battery exchange/recharge/reuse, staged heavy offload and optional thermal/housekeeping calculations are now connected to the normal job/assurance/store path. Exact behavior, engineering input contract and remaining mission-design limits are in [ENGINEERING-PROCEDURES.md](ENGINEERING-PROCEDURES.md). The current mission has no installed procedure manifest or thermal calibration profile; this is shown explicitly in Work. No test fixtures were saved into it.

Returned provider usage now reconciles before parsing tool arguments, including malformed proposals. This malformed-proposal path is regression-tested with injected responses; successful live calls do not by themselves verify malformed provider behavior.

## Inspect the actual acceptance run

- Open http://127.0.0.1:8022/ for the current isolated real-Meta run, not the paused PostgreSQL review copy on port 8021. Its banner identifies the experiment; HTTP writes and Create an experiment are disabled.
- In Agents, open the recorded Wonder/Spark response IDs, public proposals and validation results. live-responses-current.json independently matched all 71 final nominal responses; the four named fault authentication reports matched 88 more. The initial 17 are included in the 71. No uncertain request is counted as received.
- Charging policies are explicit director authorizations with pinned source versions. The corrected contract calls them evidence_ids, preventing confusion with power-source equipment. No policy is installed as a fallback.
- The longer nominal study explicitly disabled random equipment faults and failed readiness with water held. The four controlled fault comparisons completed separately; the seeded robustness runs remain a separate experiment. These are software scenarios with documented engineering assumptions, not observations of real robots.
- Keep a live SQLite database on one operating system. Use PostgreSQL across Docker/host services. The temporary Docker SQLite viewer was stopped after a read error; host integrity checks returned OK.

## What the completed acceptance actually established

- Current real provider evidence: 159 unique authenticated responses, 71 in the long nominal study and 88 in four controlled comparisons. See [live-acceptance-summary.json](live-acceptance-summary.json).
- The long mission completed power, survey, drilling, trench and shielding. Water was held by assurance and the director. It ended **not passed**, at tick 1962. Readiness and post-readiness operation are not demonstrated.
- Open the water work order on Today, then read its assurance box and latest director decision in Agents. The generic job status does not replace that retained reason. Exact provider responses and sources are in the linked reports/export.
- What is needed next: an explicit, defensible resource/production design for the hypothetical site that addresses the retained ice-yield/startup concerns, then another full readiness run. Regional consistency and imagery cannot become measured local ice concentration. Hardware/manifests/calibration gaps remain in [UNFINISHED-FEATURES.md](UNFINISHED-FEATURES.md).
- Four controlled eight-step comparisons finished; neither scheduler reached readiness in that short horizon. They do not establish autonomous superiority or full fault recovery.
