# STATUS

Owner list 1–32: see the register in [UNFINISHED-FEATURES.md](UNFINISHED-FEATURES.md) (status, evidence, next task per item).

Run checks:
- `python ../../tools/verify_stack_run.py fixed-priority 40` (from `council-dashboard/backend`): real API + worker processes, isolated database.
- `python ../../tools/verify_live_integrations.py`: live DSN Now, USGS footprints, HiRISE, Muse Image ($0.01), SAM 3.1 ($0.0025).
- `python ../../tools/archive_sources.py && python -m mission.verify_sources`: archive web sources and check every quote.
