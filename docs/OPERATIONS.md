# Operations and deployment

## Before Render provisioning

`render.yaml` is a deployment draft, not evidence of a hosted release. No Render connection, API credential, Git remote, or running Docker daemon was available during this implementation. Confirm account access, selected plan availability and the current displayed price before provisioning. Enforce the $35/month infrastructure allocation, including database storage, backups and any workspace charges. Model allocations remain $40 public + $15 experiments, with $10 reserve. No plan is represented as guaranteed capacity.

Serve the compiled frontend from the API for one origin. Set PUBLIC_ORIGIN to the exact HTTPS origin and COOKIE_SECURE=true. Store MODEL_API_KEY only on the worker. Use managed PostgreSQL and enable provider backups; perform a restore drill before a public launch. Database initialization is serialized with PostgreSQL advisory locks. Schema changes after release require reviewed migrations rather than silently changing ongoing specifications.

## Health and recovery

`GET /api/v1/health` exposes planner state, heartbeat age and source refresh status. Alert on heartbeat older than ten minutes, planning stops, source fetch failures and exhausted allowance. Simulation steps, commitments and their revision are committed in one transaction. Postgres workers use row locks; SQLite tests use BEGIN IMMEDIATE.

Planning claims survive restarts. After ten minutes, an abandoned claim is surfaced as interrupted and is not resent. Model calls use unique operation receipts. An ambiguous network failure conservatively retains its maximum reservation; review provider usage before reconciliation and `python -m mission.cli replan`. This intentionally favors no duplicate spending over automatic retry. No exactly-once guarantee is claimed for the external provider.

Source checks run every day and save immutable successful catalog versions. Failed requests preserve prior valid evidence. Sources are context only; no current Arcadia weather is inferred from Gale crater data. Regional MOLA sample is 926.19 m after decimation from 463.09 m; the optional region view exaggerates vertical relief 20× and labels it.

## Data lifecycle

Anonymous ownership is a 256-bit random cookie, HttpOnly/SameSite=Strict, stored as a hash. Private reads/exports and mutations check ownership; public writes are unavailable. Fork changes cannot alter the parent. Each owner has one unexpired experiment and a total three-sol queue allowance. Inactive forks expire after seven days and the worker deletes them. Clearing cookies loses access; there is no recovery identity in this release.

Exports contain full revision snapshots, SHA-256 state hashes, physical/cost ledgers, decision/source pins and inference receipts. Keep exported records and database backups outside ephemeral service disks. Avoid logging request headers or secrets.

## Demonstration

1. Open Today: identify objective, current job and measured reserves.
2. Open a work order and follow its power reservation, decision and pinned evidence.
3. Open Outpost and compare schematic local equipment with observed regional relief.
4. Fork the mission, prioritize habitat, and advance the bounded run. Explain why water production waits.
5. Export records and show simulator-verifiable completion. State actual inference cost and inherited foundations.
