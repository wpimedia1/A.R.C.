# Contributions and prior work

## Prior work (not claimed as hackathon work)

- **MetroDesk** — the author's earlier public project (https://github.com/wpimedia1/MetroDesk, MIT). Its ideas on distinct agents, deliberation, evidence requests and receipts informed this design. No MetroDesk code is copied. If code is copied later, record path, commit and MIT notice here.
- **Mars Council scaffold** — commit `44bd845` preserves the pre-existing FastAPI/Next.js council (three-round deliberation, trust visualization, DDPG scaffold). That code, including its offline rehearsal mode, has been removed from the working tree and is not part of the submission. It remains in Git history.

## Built during the hackathon (October 27 – November 4, 2026)

- Meta Model API integration (`mission/provider.py`, `mission/planner.py`): one credential, Responses API with strict function tools, self-contained turns (no `previous_response_id`), receipts carrying provider `response_id`, `x-request-id` and key fingerprint, cost from Meta's published prices.
- Live checks: `tools/verify_agent_loop.py`, `tools/verify_live_integrations.py`.
- Environment package and validator (`mission/package.py`, `mission/packages/arcadia-mars-v1.json`): published and derived parameters, operator-decision gate.
- Package-driven simulator (`mission/engine.py`, `mission/spec.py`): survey, trench, shielding, Rodwell water; power allocation; equipment faults; cost ledgers.
- Independent-assessment agent loop with role memory (`mission/agents.py`).
- Persistence, forks, SSE API (`mission/store.py`, `mission/api.py`).
- Evidence ingestion for MOLA, SWIM, REMS, NASA documents (`mission/science.py`, `terrain.py`, `telemetry.py`, `region.py`, `evidence.py`).
- SAM 3.1 segmentation of HiRISE imagery (`mission/media.py`, `SiteImagery.tsx`).
- Interface (`council-dashboard/frontend`), including the live 3D outpost (`MissionScene.tsx`) the user-started genesis (Start).
- Autonomous onboard agents with battery management and plan-vs-actual replanning (D10, D18); live Mars conditions, random failures, replacement logistics (`mission/conditions.py`, `logistics.py`, `route.py`, `engine.py`).
- Measured → estimated → checked weather nowcast (`mission/nowcast.py`, `frontend/components/Weather.tsx`).
- Deployment: `compose.prod.yaml`, `deploy/`, `.github/workflows/ci.yml`.

Git history: commit `44bd845` is the pre-existing baseline. Every later commit is hackathon work.

## Third-party assets

- NASA/JPL Perseverance 3D model (`frontend/public/models/perseverance.glb`), NASA media guidelines; no endorsement implied. Illustrative stand-in only.
- Kenney Space Kit models (`frontend/public/models/kenney`, CC0, license file included). Illustrative stand-ins only.
- Draco decoder files (`frontend/public/draco`) copied from three.js (MIT).
- HiRISE historical reference ESP_052358_2210 and site-covering ESP_056974_2205: credit NASA/JPL-Caltech/UArizona. Source bytes are not committed. NASA/UArizona source and media terms apply; a complete redistribution/license audit remains open.
- `meta-sam-parser` (Meta Platforms, SAM License) parses SAM 3.1 output; `pillow` reads image dimensions.
- Phosphor icons; npm and PyPI dependencies under their own licenses; The GPL-3.0 `iapws` runtime dependency was removed; density now uses a cited NIST published value. No claim of a complete third-party license audit is made.
- Scientific sources are cited in the environment package. Public availability is not blanket redistribution permission; raw datasets are not committed.

## November 3 repair verification

The changes in this working tree are uncommitted. New repairs include finite water allocations, rover reference battery accounting, component envelopes, director memory, preserved upgrades, MCD ingestion, private experiment controls, source-outage isolation and evidence image serving. See REPAIR-GUIDE.md for tested behavior and remaining work. Authenticated GET retrieval matched 51 historical records to Meta response identity, model, usage and public tool calls. One response ID returned HTTP 404; three records had no retrievable response ID. These four remain unverified. This does not validate the repaired planner through new generation; see historical-response-check.json. The initial local-only pass made no generation calls. Following owner authorization, the isolated engine-9 run produced 67 real Wonder/Spark responses, all independently matched through Meta retrieval. No new SAM call was made. Unit tests include injected model responses; their results must not be described as live provider verification.

- Independently retrieved site image: HiRISE ESP_056974_2205 (2018-09-21), credit NASA/JPL-Caltech/UArizona. USGS selection and PDS projection bounds were checked in this repair; no segmentation result was invented. Ground references, source/label hashes and pixel bounds are in hirise-ground-verification.json.

- Engine-9: staged maintenance/offload work orders, serial spare manifests and exchange/charging reuse; static load and kinematic checks; lumped thermal/housekeeping solver with optional pinned MCD coupling; explicit private engineering/fault controls; malformed-proposal usage settlement; source-hashed NASA/NIST reference metadata. No hardware qualification is claimed; provider execution is verified separately from procedure/physics unit tests.

- Engine-10: explicit source-cited charging policies; memory-only sol consolidation; calculated pinned experiment clocks; exact image-version cache keys; read-only acceptance viewing. Real acceptance found and repaired bibliographic/equipment-ID confusion and duplicated snapshot context overflow. First 17 corrected-run provider outputs were independently matched; full workflow outcomes remain in their actual acceptance reports.

- Final current-code provider result: 159 distinct responses authenticated (71 nominal, 88 controlled faults). The nominal readiness gate **failed**, with water held after five initial jobs completed. This result is not presented as full mission completion. Full evidence: live-acceptance-summary.json. The live Records projection was subsequently optimized and locally regression-tested; its changes are distinct from provider-generation proof.
