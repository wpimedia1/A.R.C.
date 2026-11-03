# STATUS

See the register in [UNFINISHED-FEATURES.md](UNFINISHED-FEATURES.md) (status, evidence, next task per item).

Run checks:
- `python ../../tools/verify_stack_run.py fixed-priority 40` (from `council-dashboard/backend`): real API + worker processes, isolated database.
- `python ../../tools/verify_live_integrations.py`: live DSN Now, USGS footprints, HiRISE, SAM 3.1 ($0.0025).
- `python ../../tools/archive_sources.py && python -m mission.verify_sources`: archive web sources and check every quote.
- `python tools/verify_live_stack.py` (from the repository root, Docker stack running and the mission started): localhost API, PostgreSQL, worker restart and a Meta-planned experiment.
- `python tools/verify_postgres.py` (Docker stack running): pg_dump / pg_restore drill into an isolated database, never production.
- `python tools/audit_repository.py`: scans the tracked files for the key in `backend/.env` and other committed secrets.
