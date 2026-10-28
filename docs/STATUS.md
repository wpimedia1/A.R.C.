# Implementation status — October 28, 2026

Implemented: deterministic connected mission; separate resource/cost accounting; transactional snapshots and revision hashes; worker; SSE; owner-isolated bounded experiments; source catalog ingestion; Wonder director/Spark typed specialist tool loop; conservative daily/monthly inference caps; Today/Outpost/Work/Records interface; operational 3D schematic; USGS terrain sample; tests and deployment configuration.

Live acceptance reached readiness in the isolated test database: 20 ticks, 125 kg water, $65,000 scenario operating expenditure. Actual recorded provider usage including debugging: $0.32516625. Three rejected diagnostic requests retain $0.217287 in conservative reservations pending reconciliation. See `live-acceptance.json`. This is an acceptance result, not a controlled performance comparison.

Local verification after interruption:

- Git integrity and whitespace checks passed; no interrupted-write corruption found.
- All 16 acceptance tests passed on SQLite and on isolated PostgreSQL schemas. Container frontend compilation and TypeScript checks passed.
- A live local HTTP experiment survived API/worker restart at tick 5 and completed at tick 21 with 125 kg water, $65,000 scenario expenditure and six unique decisions. Public state stayed unchanged. See `stack-verification.json`.
- Docker Desktop, PostgreSQL, API and worker are running locally at http://127.0.0.1:8020. No remote repository push or deployment was performed.

Outstanding release gates:

- Provision and validate Render within the infrastructure allowance; no hosted release exists yet.
- Run controlled live-agent benchmarks for every fault scenario against the same initial states and accounting conventions. Baseline fault tests exist; autonomous superiority is unproven.
- Complete document-level scientific extraction and page-specific engineering requirements. Current ingestion pins catalog HTTP responses; all operational quantities remain explicit scenario assumptions.
- Independent newcomer usability test, backup/restore drill and three-minute submission recording.

These limits must stay visible in the submission. Do not describe catalog ingestion as live Arcadia telemetry or the illustrative budget as a NASA fiscal plan.
