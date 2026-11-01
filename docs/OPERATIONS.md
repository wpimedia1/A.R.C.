# Operations

- Local Windows launcher: `council-dashboard/start.bat` (API on 127.0.0.1:8000 plus worker). Stop with `stop.bat`.
- Docker: `docker compose up -d database api worker`. The worker reads `council-dashboard/backend/.env`; the API serves on 127.0.0.1:8020.
- Operator shell (from `council-dashboard/backend`): `python -m mission.cli enable-agents|replan|pause|resume|benchmark`.
- Health: `GET /api/v1/health` returns 503 with the reason if the mission cannot initialize, and reports a stale worker heartbeat.
- The public mission advances one tick (1/24 sol) per hour of real time. Planning runs at mission start, after each job completes, and after any stop or fault.
- No hosted deployment is accepted yet. See UNFINISHED-FEATURES.md.
