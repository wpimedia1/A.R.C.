# Mars Mission

A persistent, evidence-backed robotic outpost sandbox. Survey → power → excavation → water → habitat → deterministic readiness verification.

The hypothetical Arcadia site and operational quantities are scenario assumptions. NASA architectures inform the story; they are not approval or engineering certification. Observed USGS regional terrain is displayed separately from simulated local equipment and obstacles.

## Run locally

Frontend: `cd council-dashboard/frontend`, `npm ci`, `npm run build`.

Backend: `cd council-dashboard/backend`, create/activate a Python 3.10+ environment, then `pip install -r requirements-mission.txt`.

Run `uvicorn mission.api:app --host 127.0.0.1 --port 8010` and, in another terminal, `python -m mission.worker`. Open http://127.0.0.1:8010. Set `COOKIE_SECURE=false` for HTTP localhost only. SQLite is the local default; use `DATABASE_URL=postgresql+psycopg://...` for production. `docker compose up --build` provides API, worker and PostgreSQL when Docker is running.

The public mission advances one tick per Earth hour, 24 ticks per simulated sol. Experiments queue up to 72 ticks in total. All API writes require the experiment's secure anonymous session and matching revision. Public mission controls are operator CLI commands, not visitor APIs.

## Models

The default is an explicitly labeled fixed-priority baseline. Configure `MODEL_API_KEY` in the worker environment, then run `python -m mission.cli enable-agents` in the backend to enable Wonder planning and Spark specialists. Standard model IDs are used. No credential is included in the repository or container.

The validator authorizes work, reserves inputs and money, and the deterministic engine measures completion. Models cannot edit resource balances or declare readiness. Inspect `/api/v1/missions/public/export` for decisions, pinned evidence, ledger history, tool receipts and token costs. Private reasoning is not stored.

Monthly inference limits: $40 public, $15 shared visitor pool. Daily limits: $1.30 public, $0.48 visitors. Request cost is conservatively reserved before dispatch. Unknown outcomes retain the reservation and stop planning; they are not automatically retried. `python -m mission.cli replan` explicitly resumes after inspection. Validated work can finish during an inference stop.

## Verification

`python -m pytest tests/test_mission.py tests/test_planning.py tests/test_api.py -q`

`python -m mission.cli benchmark` produces deterministic baseline scenarios. `mission.verify_live` is an explicit bounded live acceptance run restricted to `sqlite:///live-validation.db`; it is not a superiority benchmark.

Run `python -m mission.evidence` to fetch catalog versions and explicitly adopt them for the public mission. The worker checks daily. Old decisions and forks retain their pins. Catalog timestamps are not Mars measurement times. The terrain sampler additionally requires `tifffile` and `numpy`; `python -m mission.terrain` extracts a bounded regional sample with byte-range receipts.

See [contribution attribution](docs/CONTRIBUTIONS.md), [operations](docs/OPERATIONS.md), and [implementation status](docs/STATUS.md). The original Mars Council is preserved in Git at `44bd845` and remains under `council-dashboard/backend/app`; it is not in the mission execution path.
