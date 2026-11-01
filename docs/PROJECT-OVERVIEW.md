# Autonomous Mission Planner and Simulator

Full project definition · October 30, 2026 · Working title, not final branding

## Document status

This document describes the owner's intended product, its requirements and the proposed technical design. It is **not a statement that these capabilities have been completed or verified**.

The current application is stopped. Generated mission records, API receipts, telemetry caches and reports were removed at the owner's request. Automatic mission initialization is disabled. Earlier claims of verified Meta activity are withdrawn; the discrepancy between local records and the owner's Meta developer account is unresolved. Historical copies and cleanup limits are documented in [UNFINISHED-FEATURES.md](UNFINISHED-FEATURES.md).

Read this document for the project's definition. Read the unfinished-feature inventory for its present gaps. Neither replaces independent acceptance testing.

## 1. Purpose and identity

The product is an autonomous planning and execution simulator for teams preparing, constructing and operating an outpost. **Mars is the first proposed environment, not the identity of the platform.** The longer-term platform should accept a supported location, mission objectives, available equipment, datasets and constraints, then coordinate a persistent team against those inputs.

The central research question is:

> Can a team of distinct AI agents coordinate a robotic establishment mission, adapt to new evidence and operational failures, and produce an inspectable account of what happened and why?

The intended application spans space and terrestrial environments. Examples include a robotic Mars precursor outpost, a lunar surface base and a remote Earth construction site. Each requires its own data and physical models; changing a location name must not imply support for a new environment.

The platform is intended to become a reliable simulator. It is not presently an engineering-certified predictor, a real robot controller, or proof that AI can safely colonize a world.

## 2. Why the owner is building it

This project extends the owner's earlier MetroDesk work on distinct agents, deliberation, evidence and retained records. The next step is to move from agents discussing a situation to agents taking responsibility for work, observing consequences and changing their plans.

The owner's motivation is that distance, transport costs, material constraints and human limitations make unmanned preparation worth investigating. The envisioned workforce includes humanoid robots, vehicles, craft and construction equipment—not only a rover moving along a route.

The project begins with the Meta hackathon but is intended to continue afterward. The owner plans later experimentation on their own hardware. The exact device and interfaces need confirmation before making compatibility claims. Docker was authorized for local portability and development; judges should use a hosted browser application rather than install Docker.

The operating principle is:

**Observe → Think → Act → Remember → repeat.**

These are system responsibilities, not merely four words in an LLM prompt.

## 3. What counts as a real agent

Each agent must have a persistent identity, an assigned responsibility, a defined view of evidence, authorized tools, an explicit work queue and durable outcome memory.

| Pillar | Required behavior | Inspectable output |
|---|---|---|
| Observe | Read authoritative state, source versions, equipment condition and relevant work results; detect missing or conflicting evidence. | Input snapshot, observation time, source references and gaps. |
| Think | Form a bounded recommendation within the agent's specialty; identify dependencies, alternatives and uncertainty. | Public recommendation and supporting calculations, without private model reasoning. |
| Act | Invoke typed tools; request work or resources; receive acceptance, rejection or execution failure. | Actual provider request identifiers, tool receipts, validator result and work-order identifier. |
| Remember | Retain what was proposed, attempted and measured; compare expected and actual outcomes on the next cycle. | Versioned role memory linked to previous events and sources. |

A role-playing response alone is insufficient. An agent's generated text must not directly update inventory, claim completed construction or establish a measurement. The execution system owns those changes.

Real tool execution does not by itself prove physical realism. A simulator result must remain distinguishable from an external measurement. If a required physical model or input is missing, the system must report that limitation rather than generate a plausible number.

## 4. Team and decision structure

The intended Meta model allocation is Wonder for mission-level reconciliation and substantial replanning, with Spark for specialist assessments and bounded operational tools. Source code previously configured `muse-wonder-1.0` and `muse-spark-1.3`; those identifiers and successful use through the owner's account require fresh provider verification. They are not certified here as available or functioning.

| Agent | Responsibility | Typical deliverables |
|---|---|---|
| Mission director | Objectives, dependencies, competing priorities and replanning. | Mission plan, chosen tradeoffs, revised work sequence and unresolved conflicts. |
| Survey and site lead | Site characterization, mapping, route qualification and uncertainty. | Survey requests, findings, qualified work areas and information requests. |
| Construction lead | Site preparation, assembly, shielding, inspection and rework. | Staged work orders, required resources and inspection requests. |
| Resource lead | Prospecting, excavation, processing and production inventory. | Pilot production requests, processing schedules and material balances. |
| Power and reliability lead | Power allocation, charging, thermal dependencies, equipment health and maintenance. | Reservations, maintenance plans and recovery actions. |
| Logistics and finance lead | Equipment delivery, supplies, spares, commitments and supported cost forecasts. | Allocations, delivery schedules and financial records. |
| Assurance lead | Independent review of evidence sufficiency, proposed completion and acceptance criteria. | Acceptance recommendation, rejection reasons or requests for missing evidence. |

These are distinct responsibilities, not necessarily separately trained models or separate physical machines. Equipment assignment depends on capabilities, availability and constraints.

### Independent assessments and council deliberation

At a material planning boundary, departments assess a common frozen observation independently. Each receives its own relevant history but does not receive other agents' current proposals or a director's preferred answer before making its initial assessment.

The director then reconciles the assessments. Disagreements and rejected alternatives remain visible. Executing calls sequentially is compatible with this independence only if their assessment inputs remain isolated and unchanged.

The purpose is to investigate premature agreement and correlated judgment. Using the same model does not automatically mean every answer has equal weight. Blinded assessments are a proposed design intervention, not proof that correlated errors have been solved.

The council should handle consequential choices and unresolved conflicts. Routine work should proceed within already authorized bounds. A model vote cannot override a physical constraint or deterministic completion check.

## 5. Mission workflow

The first intended mission begins with uncrewed equipment and cargo already delivered. Spacecraft flight simulation is outside the first release.

1. **Define the mission.** Establish the objective, supported environment, delivered inventory, equipment specifications, authority and acceptance criteria.
2. **Qualify candidate work areas.** Compare available mapping and resource evidence; identify unknowns and required surveys.
3. **Commission essential services.** Establish power, communications, localization, charging and applicable thermal protections.
4. **Survey and prospect.** Collect or ingest evidence that can qualify routes, ground conditions and accessible resources.
5. **Demonstrate production.** Run a supported pilot process before planning expansion around its output.
6. **Construct infrastructure.** Prepare sites, assemble equipment and structures, inspect results and address defects.
7. **Verify readiness.** Evaluate published mission-specific criteria through the execution and assurance systems.
8. **Continue operating.** Survey, produce, maintain, charge and expand within available resources and explicit authority.

The initial Mars work sequence previously proposed was survey → power → excavation → water → habitat → readiness. That sequence expresses dependencies, not a validated NASA schedule. Exact durations, quantities and thresholds must come from defensible inputs before they can support feasibility claims.

The Moon requires a different environment package, including applicable terrain, illumination, communications, thermal and resource constraints. A lunar mission cannot reuse Mars assumptions silently.

Readiness achieved and mission stopped are separate states. Continued operation must not imply unlimited resources or an endless loop of meaningless work.

## 6. Data and scientific foundation

### Proposed first-environment sources

These are research and ingestion targets, not a declaration that validated copies currently remain installed.

| Source | Intended use | Boundary |
|---|---|---|
| [NASA Mars DRA 5.0](https://ntrs.nasa.gov/citations/20090012109) | Mission concepts, precursor deployment and surface-operation context. | Does not supply a complete approved settlement plan or every equipment parameter. |
| [NASA Moon-to-Mars architecture citation](https://ntrs.nasa.gov/citations/20250010956) | Architectural requirements, decisions and unresolved capabilities. | Pin and verify the exact document revision and passages. |
| [SWIM](https://swim.psi.edu/) | Regional subsurface ice evidence and mapped radar interpretations. | Consistency with ice is not a measured recoverable yield. |
| [USGS MOLA terrain](https://astrogeology.usgs.gov/search/map/mars_mgs_mola_dem_463m) | Regional elevation and geographical context. | Coarse orbital data cannot establish local obstacle clearance or soil bearing strength. |
| [SICSA First Mars Outpost](https://sicsa.egr.uh.edu/sites/sicsa/files/files/publications/first-mars-outpost-compressed.pdf) | Conceptual staged infrastructure and precursor planning. | Keep its assumptions distinct from NASA architectures. |
| [Curiosity REMS archive](https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html) | Instrument observations with timestamps, locations and quality information. | Gale crater archive observations are not current Arcadia measurements. |

The owner's requested Arcadia study bounds are 33.87–64.17° N and 165.86–210.43° E. A proposed exact landing location must not be mistaken for a measured, qualified construction site.

The data model must distinguish source publication, retrieval time, observation time and applicability location. Local micro-sensors without instruments are `null` with an `uninstrumented` status. Missing coverage is not zero.

Every parameter must carry a unit, value or supported range, origin, justification and scope. Observations, published estimates and calculated values must remain distinct. Unverified assumptions require explicit identification and authorization; they cannot be silently supplied as defaults. If sufficient inputs do not exist, affected feasibility claims and actions must remain blocked or expressly limited to an authorized experiment.

Any transformation into an operational parameter must record input versions, calculation, transformation version and applicability limits. A citation attached to a generated value is not sufficient provenance.

Source failures must retain a clearly dated last valid version where one exists, or show unavailable data. They must never manufacture replacement telemetry.

## 7. Physical and financial execution

The execution engine must validate work before reserving resources. Validation includes prerequisites, equipment compatibility, availability, physical inputs, energy, storage and spending authority.

Travel, excavation, processing, construction and maintenance need different supported consequences. For example, processing must conserve accounted material through documented outputs and losses; construction must consume defined inputs and advance an inspectable stage.

Routes must use appropriate terrain and obstacle information. Regional elevation context is not sufficient evidence for a drivable path. Humanoid, vehicle and craft capabilities require dedicated models or validated external adapters; illustrative 3D assets do not provide those capabilities.

Physical and monetary ledgers are separate. Financial records must distinguish capital, commitments, operating expenditure and actual inference usage, with currency year and scope. Historical program budgets must not be repurposed as fabricated prices for robotic jobs.

The owner manages spending policy. The implementation should use appropriate request sizing, bounded tool loops, caching and planning cadence for responsiveness and reliability, without imposing unrequested financial ceilings.

## 8. Records, provenance and failures

Each operational result must be traceable through:

**Requirement/source → input snapshot → calculation → agent proposal → validation → action → result.**

Records should include source URLs, exact versions and passages where applicable, hashes, timestamps, transformations, provider request/response identifiers, tool arguments, public summaries and execution outcomes. Credentials and private model reasoning must not be stored in public records.

Application receipts need independent provider corroboration. Request hashes and response-shaped JSON generated locally do not prove a request reached the user's account.

Failures must identify the affected operation, what is known, what is uncertain and what recovery is allowed. An interrupted request must not be replayed blindly. Unsupported model claims cannot become authoritative state. A stopped planner must be visible even if the HTTP service remains healthy.

Old source versions and mission revisions must remain interpretable across upgrades. Current deletion instructions take precedence over the normal retention design; removed records must not be reconstructed as if they were original evidence.

## 9. User experience

Preserve the navigation and plain-language format the owner accepted. The interface should answer: **What is the plan? What is happening? Why? How? What evidence supports it?**

| Surface | User purpose |
|---|---|
| Today | Understand the objective, active work, critical blocker, latest decision and next milestone. |
| Outpost | Explore equipment, construction stages, routes and terrain with a non-3D alternative. |
| Work | Inspect assignments, prerequisites, reservations, actual progress and clearly labeled forecasts. |
| Agents | Inspect independent assessments, information gaps, reconciliation, tool activity and outcome memory. |
| Evidence | Explore maps, measurements, source passages, dates, uncertainty and transformations. |
| Records | Follow provenance, failures, historical changes and exports. |

Use readable typography, strong contrast and meaningful status colors. Keep model diagnostics and algorithm terminology inside inspection views rather than making them the primary navigation language.

The 3D view must reflect authoritative persisted state. It must not animate successful work that has not occurred in the execution system. Concept imagery must remain labeled illustration and cannot replace observational evidence.

Actual and predicted timelines must be distinct. Empty, disconnected, stale, failed and uninstrumented states require clear explanations rather than sample values.

## 10. Technical architecture

The intended architecture retains useful existing plumbing while replacing the original toy orchestration.

- **Frontend:** Next.js/React and TypeScript; React Three Fiber/Three.js for spatial inspection.
- **API:** FastAPI with versioned `/api/v1` interfaces and owner-controlled mutations.
- **Persistence:** PostgreSQL for mission state, revisions, work, resource accounting, sources and receipts.
- **Worker:** dedicated operational process for transactional job execution, planning boundaries, ingestion and recovery.
- **Updates:** reconnectable server-sent events with authoritative snapshots for resynchronization.
- **Model adapter:** explicit authenticated Meta requests with typed tools, durable request status and provider-correlated verification.
- **Environment and equipment adapters:** validated input packages with declared capabilities and applicability limits.

The intended records include `Mission`, `MissionSpec`, `Asset`, `Job`, `ResourceReservation`, `Observation`, `SourceVersion`, `Transformation`, `Decision`, `AgentMemory`, `LedgerEntry`, `InferenceReceipt` and `MissionEvent`. These describe required concepts; not all currently exist as independent database tables.

Required interfaces cover mission state, assets, work, agent activity, evidence, resource history, events, schedule, fork comparison and export. Fork creation, configuration and pause/resume require ownership checks. Visitors cannot mutate the public mission.

The earlier DDPG/trust-clustering and three-round scaffold must not be presented as the operational system. Existing source may be referenced or adapted only with explicit attribution and verification.

## 11. Persistent operation and experiments

The intended public mission persists between visits and advances at a declared pace. The prior product specification selected one simulated sol per Earth day; that is a product pacing choice, not a physical measurement or NASA mission schedule.

Private experiments should fork a specific revision and pinned evidence. Allowed changes include priorities, equipment availability, supported production inputs and spending authority. Results must be compared with an equivalent starting state and elapsed time.

The original release design proposed anonymous secure ownership, one active fork per visitor, bounded experiment duration and expiry. These controls require verification and must remain distinct from the owner's provider-spending decisions.

Model calls belong at planning boundaries and material exceptions, not animation frames. Restarting a service must not duplicate jobs or provider requests. Long-term operation requires monitoring, backups, retention, alerts and explicit degraded states.

## 12. Validation and acceptance

Acceptance requires observed behavior and inspectable evidence, not backend test counts alone.

- Correlate real application requests with the owner's provider account before making any live-model claim.
- Demonstrate independent assessment inputs, role-specific memory and actual authorized actions across multiple cycles.
- Verify resource conservation, no double spending, prerequisites, equipment authority and completion criteria.
- Verify source identity, units, coordinates, freshness, missing values and transformation correctness.
- Demonstrate that missing information or provider failure produces a clear, recoverable state without mock substitution.
- Verify restart recovery, concurrent claiming, source pinning, replay, ownership and fork isolation.
- Compare nominal and fault scenarios under matched initial conditions, reporting outcomes without assuming agent superiority.
- Test the visible journey on desktop, mobile, keyboard and assistive interfaces; conduct a newcomer usability review.
- Verify backup/restore, secret handling, dataset and asset permissions, and repository size limits.
- Complete a local owner review before publication or hosting.

Passing a deterministic simulator test does not establish that a real excavator will achieve its modeled yield. Provider integration, scientific validity, engineering fidelity and product usability are separate acceptance questions.

## 13. Attribution, distribution and submission

MetroDesk is the owner's prior work and inspiration. The preserved Mars Council scaffold is also pre-existing. Submission materials must distinguish those foundations from new implementation and identify any directly reused code, original commit and license. Existing attribution entries require verification rather than blind reuse.

Respect dataset terms, asset licenses, document copyrights and attribution requirements. Publicly accessible material is not automatically licensed for unrestricted redistribution. Keep large datasets, credentials, databases and build outputs outside the submission repository; the owner's repository limit excludes files over 100 MB.

The intended judging experience is a browser-accessible application with a concise narrative and inspectable records. The explanation should cover the motivation, agent loop, actual work, evidence, limitations and new contributions. It must not represent a prototype as a completed autonomous colonization system.

Local acceptance comes before GitHub publication and deployment. The owner has explicitly held commits and pushing pending discussion/review. No publication is authorized by this document.

## 14. Delivery sequence and present boundary

The appropriate sequence is provider/account verification → defensible inputs and clean state → validated execution → agent operation → usable provenance and interface → integrated fault testing → local acceptance → submission and approved deployment.

The current code is not at that acceptance boundary. It is deliberately stopped after the requested record removal. The comprehensive gap list, including historical-copy cleanup limits, is [UNFINISHED-FEATURES.md](UNFINISHED-FEATURES.md).

This project aims to investigate reliable autonomous teamwork. Its credibility depends on showing actual evidence, acknowledging unknowns and refusing to substitute generated appearances for demonstrated capability.
