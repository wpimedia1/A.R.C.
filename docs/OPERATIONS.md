# Operations

- Docker (local): `docker compose up --build -d database api worker`; open http://127.0.0.1:8020/. The worker reads `council-dashboard/backend/.env` for `MODEL_API_KEY`.
- Docker (cloud host): see "Deploy" in the README (`compose.prod.yaml`, HTTPS, required secrets).
- Local Windows launcher without Docker: `council-dashboard/start.bat` (API on 127.0.0.1:8000 plus worker); stop with `stop.bat`.
- Nothing runs until the operator presses **Start mission** in the app with the operator token (genesis, D17). Docker reads `MISSION_OPERATOR_TOKEN` from `.env` in the repository root; the local launcher reads it from `council-dashboard/backend/.env`.
- Upgrades: a mission recorded under another package or engine version is archived (`archive-<time>-<package>`, read-only, full revision history, export at `/api/v1/missions/<id>/export`) and Start begins a new genesis beside it. Do not delete the database volume to upgrade.
- Operator commands (inside Docker: `docker compose exec worker python -m mission.cli <action>`):
  - `replan`: clear a planning stop and ask the agents to plan again.
  - `pause` / `resume`: pause or resume the public mission.
  - `retry-site-analysis`: run SAM site analysis again after a recorded failure.
  - `enable-agents`: switch a mission to Meta agents. `benchmark`: fixed-priority baseline runs (no model calls).
- Health: `GET /api/v1/health` reports whether the mission has started, the worker heartbeat, archived missions, whether an operator token is configured, and 503 with the reason if the package cannot load.
- Pace: the public mission advances one step (1/24 sol, about 61.6 minutes) per Mars hour of real time. Agents run onboard and plan at genesis, after each job completes or a fault, on a low battery, when work falls behind its authorized rate, at solar conjunction, at a change of season and on resume.
- Spending: visitor experiments may not spend Meta credits unless `MISSION_VISITOR_DAILY_LIMIT_USD` / `MISSION_VISITOR_MONTHLY_LIMIT_USD` are raised (default 0, local and cloud). Visitors can end their own experiment from the experiment bar.
