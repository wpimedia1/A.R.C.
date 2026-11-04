# Engineering procedures and equipment physics

This implementation adds executable repair, battery exchange, spare charging and heavy-payload placement to the deterministic mission engine. It does **not** claim that an existing Mars repair arm, battery interface or 90-ton offload station has been qualified. No fabricated engineering manifest is installed in the public mission or review copy. Test fixtures remain in temporary test databases.

## What executes

- **Repair:** reserve a diagnosed failed target, compatible service equipment and an individually identified spare module. Run the configured stages through normal power reservation and assurance. Install the spare, retain the removed failed part, restore the target and record the result. Unknown aggregate equipment failure does not become an invented component diagnosis.
- **Battery exchange:** reserve a compatible charged pack and service equipment. At completion, move the old pack, including its remaining charge, into the manifest; move the new pack into the vehicle. Swapping neither charges batteries nor manufactures spare packs.
- **Spare charging:** reserve a removed pack and charging equipment; integrate grid power over actual stage overlap and apply the declared efficiency. Stop consuming power when full. The pack can then be exchanged back into the vehicle. Installed and stored charge are represented separately.
- **Offload:** require known payload mass, compatible lifting equipment, prepared trench and power. Validate payload rating, factored cable load, restoring and structural moments, descent braking capacity and travel/speed duration. Reserve the payload and service equipment, execute stages and place the payload at the prepared site. Shielding and readiness cannot bypass an outstanding payload placement, including before an offload order is created.
- **Failure/recovery:** grid loss, service-equipment failure or a changed target diagnosis stops work. Progress and spare reservations persist. Reauthorization resumes from recorded progress. Serialized or database recovery does not repeat a completed exchange or charge.
- **Costs:** extra manifest items with no price remain explicitly unestimated. They do not silently become free stock. A supplied price requires USD quantity provenance, currency year and scope.

Procedure jobs use the same `start`, onboard assurance, `advance`, ledgers, transaction claims, revisions and exports as other jobs. Meta agents can inspect installed designs and create compatible procedure jobs through typed tools; they cannot install engineering parameters or edit inventory balances. Director-created job IDs are appended deterministically after its existing-job priority list.

## Configure and run

- Open the public review and create a private experiment. The normal public mission remains read-only.
- Expand **Work priorities and experiment allocations → Engineering design and service work**. Import a JSON object containing `procedures` and/or `equipment_physics`.
- Choose a configured procedure, compatible service equipment and a stored spare serial. Create its work order. This reserves stock and the target; it does not mark work complete.
- Choose the intended planner and run a bounded experiment. Fixed-priority mode is explicitly deterministic and never presented as Meta activity. Agent mode requires an actual provider call and normal assurance.
- Inspect the job, stage durations, recorded energy, spare manifest, input snapshot, profile/configuration hashes and result. Export the mission to retain the full history.
- A controlled component-failure button is available for a configured repair study. Its record is explicitly `operator-injected scenario, not telemetry`; it does not create a sensor observation.

For API clients, use the existing owner-scoped `POST /api/v1/missions/{id}/control` with `action: configure`, current `revision` and the corresponding `changes` object. Public and other visitors' missions reject these writes. Normal run/pause controls are unchanged.

## Engineering manifest contract

Every numeric input is an object with `value`, exact `unit`, `origin` and `justification`. Origins are `observed`, `published estimate`, `calculated`, or `scenario assumption`. Non-scenario quantities require a known source ID and passage locator. Calculations also require `formula` and `inputs`; assumptions require explicit `approved: true`. A citation records the operator's asserted applicability; the application does not certify a hardware design by accepting a URL.

`procedures` contains:

| Field | Required content |
|---|---|
| `profiles` | One to 24 profiles: unique `id`, `kind`, `title`, `target_id`, `interface`, and one to 16 stages |
| Each stage | Unique `name`, `duration` quantity in `h`, `grid_power` quantity in `kW` |
| `service_equipment` | Existing equipment IDs mapped to interface, explicit approval and applicability justification. This is a declared engineering design, not automatic installation of physical tooling. |
| `inventory` | Unique serial IDs, `module` or `battery`, interface, compatible asset ID, approved manifest basis. Batteries require capacity and initial-charge quantities in `Wh`; modules identify their component. |
| Repair profile | Exact diagnosed `component` matching its spare |
| Charge profile | `charge_efficiency` quantity in `1`, greater than zero and at most one |
| Offload profile | `rated_payload` in `kg`, initial location `lander`, explicit support/stability/attachment assertions and verification basis, and `lifting` inputs below |
| Optional spare price | `capital_cost` quantity in `USD`, `currency_year`, `cost_scope` |

Offload `lifting` requires quantity inputs `gravity` (`m/s2`), `travel` and `reach` (`m`), `speed` (`m/s`), `restoring_moment` and `structural_moment_limit` (`N m`), `cable_load_limit` (`N`), `braking_capacity` (`W`), `safety_factor` (`1`, at least one), and the named `motion_stage`. Offload also requires `rotation`: initial/final angles in `deg` (vertical toward horizontal, 0–90), `angular_speed` in `deg/s`, `cg_offset` in `m`, `torque_limit` in `N m`, and a named `rotation_stage`. Rotation time, factored gravitational torque and combined rotational/translational braking are checked. Persisted orientation/descent drive the illustrative payload transform. The equations are F = mg, overturning moment = F × reach, minimum motion time = travel/speed, and descent braking power = F × speed. These are static vertical-lowering constraints and bounded rotation kinematics; they do not cover flexible structures, wind, foundation bearing, flexible-body habitat rotation or certification. Boolean verification fields are operator assertions, not independently observed engineering approvals.

Configuration is immutable once installed. Fork before changing a design or stock manifest; this prevents resetting consumed spares. The current Arcadia package still starts with the D4 preplaced-habitat assumption until an explicit offload study is configured. That baseline cannot demonstrate heavy offloading. Selecting and validating compatible service hardware remains an open mission-design task.

## Thermal and electrical model

`equipment_physics` maps battery-equipped asset IDs to component profiles. Each requires a published temperature-envelope `variable` and these quantities:

| Input | Unit |
|---|---|
| `heat_capacity` | `J/K` |
| `conductance` | `W/K` |
| `radiating_area` | `m2` |
| `emissivity`, `heat_fraction` | `1`, between zero and one |
| `initial_temperature`, `ambient_temperature`, `radiative_temperature`, `heater_setpoint` | `K` |
| `housekeeping`, `heater_max`, `absorbed_solar` | `W` |

The model solves C ΔT/Δt = P − K(T−Ta) − εσA(T⁴−Tr⁴) with a monotone implicit interval. Housekeeping has battery priority; the thermostat requests bounded heater power from remaining stored energy. Brownouts cannot generate heat or motion. Each receipt records the energy draw, previous/new temperature, input profile hash and heat-balance residual. Results are labeled calculated engineering scenarios, never internal sensor readings. The current working set keeps 24 thermal receipts; earlier receipts remain in append-only mission revisions.

An optional `climate_boundary` names `version_id` and `variable: air_temperature_k`. The server resolves it against the mission-pinned MCD source, requires full 0–24-hour coverage and stores the actual source hash/samples. Each step interpolates at calculated site solar time and records its bracketing samples. It uses pinned climatology as a model boundary, not current Arcadia weather. The effective radiative temperature remains a separate explicit input; surface air is not silently relabeled sky temperature. A retained profile does not automatically switch to later source releases.

The heat balance follows [NASA thermal-control guidance](https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/); σ comes from the actual [NIST CODATA table](https://physics.nist.gov/cuu/Constants/Table/allascii.txt). Raw retrieval hashes, source versions and the rounded constant are bundled in `mission/physics-references.json`; raw documents remain outside Git. No thermal geometry, conductance, housekeeping load or battery-aging calibration is invented for the current outpost. Terrain-dependent loads, multi-node thermal analysis, degradation, transport and qualified machinery designs remain open.

## Reference applicability

The [NASA heavy-habitat paper](https://ntrs.nasa.gov/citations/20220010430) identifies concepts needing further design work. Its existence does not supply a qualified crane time or integrated lifting hardware. [NASA modular excavator concepts](https://ntrs.nasa.gov/citations/20210012148) and [MICE](https://ntrs.nasa.gov/citations/20240003128) support modular service interfaces, without establishing a RASSOR repair station. The [Ocado datasheet](https://139494159.fs1.hubspotusercontent-eu1.net/hubfs/139494159/Datasheets%20Download/OIA_BatterySwapUnit_datasheet_2024_v2.pdf) describes terrestrial equipment; its timings are not installed as Mars defaults.

The test suite uses declared synthetic engineering inputs to verify software conservation and rejection paths. Those tests are neither Mars measurements nor evidence of a fresh Meta-directed execution. See the local verification report for exact current test/browser results and the gap register for remaining mission-level acceptance.


## Engine-10 standing orders and time

Routine grid charging can be authorized by the director or power lead through `set_charging_policy`. The condition is the source-rated energy needed for one work interval; all existing grid, component and service-lock checks still apply to each execution. No policy is installed silently. Every authorization and execution has an actor and record. Repeated identical blockers do not generate repeated policy events. Planned charging time is excluded from false behind-plan alarms.

At a sol boundary, existing working memory requests Spark consolidation without forcing a new director meeting. Memory-only work has a durable planning claim and provider receipts, but does not invent a new mission plan or independent assessment round. Changed resources, equipment, evidence and milestones still request full planning.

Agents and private/replay scenes use a calculated clock from the pinned mission epoch plus elapsed steps. Source observation timestamps remain unchanged. Ground texture requests include their exact source version; a snapshot/source mismatch rejects rendering rather than displaying an older cached raster under a newer citation.

The initial engine-9 provider run and its source hashes remain preserved in `live-agent-loop-engine9.json`, `live-mission-engine9-paused.json` and `live-responses-engine9.json`. Its 67 real responses all matched Meta retrieval. It stopped for orchestration improvements, not readiness. Engine-10 results must be checked separately; current build/test output is authoritative while acceptance is in progress.
