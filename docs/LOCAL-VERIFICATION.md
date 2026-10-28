# Local verification — October 28, 2026

Interruption recovery found no Git object corruption or whitespace errors. The original baseline remains at `44bd845`; mission implementation checkpoint is `ef4aba6`.

## Executed checks

- SQLite/API acceptance suite: **16 passed**, 7.61 seconds.
- Docker PostgreSQL acceptance suite: **16 passed**, 6.07 seconds. Each test uses its own temporary schema, preserving the public database.
- Linux container frontend build: compilation, TypeScript validation and static export passed.
- Local health endpoint: `status=ok`, `worker_stale=false`, explicitly `model_calls_enabled=false` for the public baseline.
- Five evidence catalog responses retrieved and pinned. Catalog retrieval does not establish current Mars weather or site measurements.
- API/worker replacement and mid-experiment restart: recovered at tick 5, completed at tick 21, 125 kg water, $65,000 scenario expenditure, six unique decisions, unchanged public snapshot. Machine-readable receipt: `stack-verification.json`.
- Browser: opened the PostgreSQL-backed app, resumed a private experiment, ran one sol, observed six completed milestones, inspected the readiness work order and pinned scenario evidence, and returned to the unchanged public mission. No browser console errors were recorded in that check.
- Separate actual Meta-agent acceptance run reached readiness; receipts are in `live-acceptance.json`. It was not a controlled comparative benchmark.

## Boundaries

The default local demo is the labeled deterministic baseline. Science catalogs and regional elevation are real sources; the local terrain, equipment capacities, production rates and operating prices are scenario assumptions. Scientific passage extraction, controlled autonomous fault benchmarks, backup restoration, newcomer usability testing, visual asset polish and hosted operation remain release work. Nothing was pushed or deployed remotely.

See the README for setup, run, verification and stop commands.
