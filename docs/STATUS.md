# Implementation status — October 28, 2026

Implemented: deterministic connected mission; separate resource/cost accounting; transactional snapshots and revision hashes; worker; SSE; owner-isolated bounded experiments; source catalog ingestion; Wonder director/Spark typed specialist tool loop; conservative daily/monthly inference caps; Today/Outpost/Work/Records interface; operational 3D schematic; USGS terrain sample; tests and deployment configuration.

Live acceptance reached readiness in the isolated test database: 20 ticks, 125 kg water, $65,000 scenario operating expenditure. Actual recorded provider usage including debugging: $0.32516625. Three rejected diagnostic requests retain $0.217287 in conservative reservations pending reconciliation. See `live-acceptance.json`. This is an acceptance result, not a controlled performance comparison.

Outstanding release gates:

- Run the transactional suite against PostgreSQL; local database verification used SQLite because Docker was unavailable.
- Provision and validate Render within the infrastructure allowance; no hosted release exists yet.
- Run controlled live-agent benchmarks for every fault scenario against the same initial states and accounting conventions. Baseline fault tests exist; autonomous superiority is unproven.
- Complete document-level scientific extraction and page-specific engineering requirements. Current ingestion pins catalog HTTP responses; all operational quantities remain explicit scenario assumptions.
- Independent newcomer usability test, backup/restore drill and three-minute submission recording.

These limits must stay visible in the submission. Do not describe catalog ingestion as live Arcadia telemetry or the illustrative budget as a NASA fiscal plan.
