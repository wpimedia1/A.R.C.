# Contributions and prior work

## Prior work (not claimed as hackathon work)

- **MetroDesk** — the author's earlier public project (https://github.com/wpimedia1/MetroDesk, MIT). Its ideas on distinct agents, deliberation, evidence requests and receipts informed this design. No MetroDesk code is copied. If code is copied later, record path, commit and MIT notice here.
- **Mars Council scaffold** — commit `44bd845` preserves the pre-existing FastAPI/Next.js council (three-round deliberation, trust visualization, DDPG scaffold). That code, including its offline rehearsal mode, has been removed from the working tree and is not part of the submission. It remains in Git history.

## Built during the hackathon (October 27 – November 4, 2026)

- Meta Model API integration (`mission/provider.py`, `mission/planner.py`): one credential, Responses API with strict function tools, `previous_response_id` chaining, receipts carrying provider `response_id`, `x-request-id` and key fingerprint, cost from Meta's published prices.
- Live checks: `tools/verify_agent_loop.py`, `tools/verify_live_integrations.py`.
- Environment package and validator (`mission/package.py`, `mission/packages/arcadia-mars-v1.json`): published, derived and IAPWS-computed parameters, operator-decision gate.
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
- HiRISE image ESP_052358_2210: NASA/JPL-Caltech/UArizona, public domain (credit given in the interface). Loaded from the HiRISE PDS server; not committed.
- `meta-sam-parser` (Meta Platforms, SAM License) parses SAM 3.1 output; `pillow` reads image dimensions.
- Phosphor icons; npm and PyPI dependencies under their own licenses; `iapws` (GPL-3.0) is a runtime dependency — confirm license compatibility before redistribution.
- Scientific sources are cited in the environment package. Public availability is not blanket redistribution permission; raw datasets are not committed.
