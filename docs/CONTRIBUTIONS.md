# What we built during this hackathon

## Preserved pre-existing baseline

Commit `44bd845` preserves the original Mars Council source before the mission rebuild: FastAPI, Next.js/React, model-request patterns, three-round deliberation, trust visualization, DDPG scaffolding, and toy simulation. The operational mission imports none of the DDPG/trust/council execution code. Original files remain inspectable in Git.

## MetroDesk inspiration

MetroDesk is the author's existing public project: https://github.com/wpimedia1/MetroDesk. Reference reviewed: commit `23c3bdd2c80d785baa0177a83184281e4bf85ec0`, MIT repository. Its deliberation, evidence requests, verified objections, public summaries and receipt patterns informed this design. No MetroDesk source code was directly copied into this implementation. Consequently there is no adapted MetroDesk code block to attribute; if a later change copies code, record its path, original commit and MIT notice here.

## New implementation

- `backend/mission`: independent mission specification, action-specific deterministic simulator, physical and financial accounting, resource validation, transactional revisions, private forks, SSE API, dedicated worker, source version ingestion, bounded Meta tool requests, cost reservations and receipts.
- New TypeScript mission UI: Today, Outpost, Work, Records, state-driven React Three Fiber scene, accessible equipment list, decision inspector and export.
- Real USGS MOLA regional sample retrieved by HTTP range, with original resolution, resampling, bounds and hashes. Local outpost terrain remains explicitly simulated.
- New acceptance tests, live acceptance receipts, baseline benchmark, container configuration and Render deployment draft.

Product Design generated the selected briefing and atlas reference images before coding. New code-rendered scene assets are schematic representations, not NASA equipment models. Fonts are Google Fonts DM Sans and Libre Caslon Display; Phosphor provides interface icons; npm dependencies retain their own licenses.

## Submission disclosure

Show the old MetroDesk/Mars Council foundations briefly, then demonstrate the new simulation and operating system. Do not claim existing work, external scientific datasets, generated design references or dependency code as newly authored research. Do not claim the baseline benchmark proves autonomous planning superiority.
