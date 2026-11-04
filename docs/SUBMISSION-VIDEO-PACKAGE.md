# A.R.C. — proof-of-capability video package

Prepared November 4, 2026. YouTube landscape, 1920 × 1080, exactly 3:00.

**Demonstrated claim:** inspect a recorded Meta-generated survey work order, its cited input, validation, authorization and simulator outcome through the application and supporting records.

**Boundary disclosed immediately:** this is read-only inspection of an accelerated software study. No robots are controlled and no new inference is presented as occurring during the recording. Published rover performance is a reference operating point, not verified performance at this hypothetical site. The selected record retains missing obstacle-clearance and complete energy-model conditions.

This package deliberately excludes full-mission feasibility/readiness, physical navigation, water-system validation, repair, swapping, offload, private experiments and decorative 3D movement. Their missing integration or physical-model limitations cannot be represented as demonstrated capability.

## 1. Video structure

| Time | Purpose | Screen evidence |
|---|---|---|
| 0:00–0:15 | Establish the problem and demonstration boundary | Actual selected survey work-order drawer; read-only inspection label |
| 0:15–0:35 | Establish the input and its interpretation | `rover.max_drive_m_per_sol`, quotation, source and “Record, not typical” note |
| 0:35–0:55 | Show the director's concrete output | Wonder `create_job` receipt and returned response identifier |
| 0:55–1:25 | Follow specialist action and assurance | Spark `submit_work_order` and `review_work_orders`; retained open condition |
| 1:25–1:50 | Show the measured software outcome | D8 drawer: accepted validation, completed job, input/calculation/result; 175.15 m |
| 1:50–2:15 | Establish traceability | D8 cited source-version identifiers and Records decision entry |
| 2:15–2:40 | Correlate the stored provider response | Original response-authentication report; selected IDs, identity/model/usage/tool comparison |
| 2:40–3:00 | Explain the demonstrated value and conclusion | Selected complete work order and explicit software/model boundary |

Use eight screen sections with direct navigation. Editorial holds at 1:25–1:35, 1:35–1:50 and 2:25–2:40 use actual read-only interface captures to keep validation, outcome and provider comparisons readable. No stock footage, generated Mars footage, music, avatars, simulated mouse activity or invented success screens. Captions identify recorded evidence. All visible application state is the real saved state. Holds do not depict a new mission run.

## 2. On-screen action script

### Recording preparation

- Use the existing completed acceptance database `output/live-acceptance/run-eh7lirlp/agent-loop.db`, mission `public`, revision **2021**, tick **1976**, status **paused**.
- The recording helper serves the unchanged application against SQLite `mode=ro`, with `ACCEPTANCE_READ_ONLY=1`, on `http://127.0.0.1:8031/`. It does not start a worker or load a substitute scheduler.
- Server command from the repository root: `council-dashboard/backend/.venv/Scripts/python.exe -u -B output/demo/serve_readonly.py`.
- Capture the browser at 1280 × 720 and scale uniformly to the 1920 × 1080 delivery frame for readable text. Keep the inspection/paused status visible when framing permits. Add a persistent editorial label: **Recorded software study · read-only inspection · synthetic narration**.
- Use one browser tab. At the report section, open `http://127.0.0.1:8031/_demo/report/responses`; it serves the original saved report, not a new provider query. Return to the application URL for the conclusion.
- Do not enter credentials, change mission settings, start agents, fork, resume or inject failures.

| Time | Screen | Exact sequence: mouse, pages, data and buttons | Output to frame |
|---|---|---|---|
| 0:00–0:15 | Work-order drawer | In the application click **Work**. In the schedule click **Extend the site survey by one sol of driving**. Keep this drawer open for the first shot. No data entered. | Job title, owner `survey`, status `complete`, progress and simulator framing. Do not show unrelated water figures as an accomplishment. |
| 0:15–0:35 | Records parameter | Press Escape. Click **Records**. Use browser Find for `rover.max_drive_m_per_sol`; exit Find. Expand that parameter's summary. No application data entered. | Exact value `175.15 m/sol`, source/locator/quotation and `Record, not typical` note. The source URL is visible; a link is not represented as a fresh source retrieval. |
| 0:35–0:55 | Agents | Click **Agents**. Under **Actual API requests**, expand the `muse-wonder-1.0` receipt dated **11/4/2026, 12:16:15 PM Eastern**. Verify response ID `resp_6aeb686dcea3768717514d9a` after expansion. | `create_job`, template `survey-extension`, actual public arguments and returned provider response ID. Do not label this as a new live request. |
| 0:55–1:25 | Agents | Expand the Spark receipt dated **12:21:36 PM Eastern**: response `resp_6aeb69ae8dac53841e334690`, `submit_work_order`. Frame `job_id`, `asset_ids`, `source_ids`. At 1:09 expand the Spark receipt dated **12:21:51 PM Eastern**: response `resp_6aeb69c60b1701040a524919`, `review_work_orders`. | Work order `survey-extension-1`, rover `rover-1`, cited sources, explicit acknowledgement `no-site-imagery`, and the review's simulator-only qualification. |
| 1:25–1:50 | Work-order drawer | Click **Work**, then **Extend the site survey by one sol of driving** in the schedule. Frame the validator line, then expand **Input snapshot and calculation**. Scroll inside the drawer to the end of its JSON so `result` is readable. No data entered or execution button pressed. | D8 `validation: accepted`, outcome `completed_tick: 1976`, `survey_m_survey_extension_1: 175.15`, configured target/rate. Narrate zero *grid* draw distinctly from rover energy. |
| 1:50–2:15 | Drawer, then Records | Scroll within the drawer to **Evidence cited**. Show the exact pinned identifiers. Click **Inspect all records**. Find the D8 decision entry. | Source → parameter/input → proposal/validation → completed outcome. These are audit references, not proof of physical source applicability. |
| 2:15–2:40 | Original report | Open `http://127.0.0.1:8031/_demo/report/responses`. Frame `stored_records: 89`, `verified: 89`, `not_verified: 0`. At 2:25 find `resp_6aeb69ae8dac53841e334690`, then scroll down to place the entire selected entry above the captions. | `http_status: 200`, matching response/model, `identity_matches`, `model_matches`, `usage_matches`, `public_tool_calls_match`. Explain that this is a saved authenticated-retrieval report. |
| 2:40–3:00 | Application | Open `http://127.0.0.1:8031/`, click **Work** and reopen the selected survey drawer. Hold the complete status and title. | Final statement: an inspectable software work-order loop; no physical navigation, complete energy-model or colonization-feasibility claim. |

The 175.15 m figure is exact in stored data; the UI rounds its compact progress display to 175.2. Use the calculation/result view for the exact value. The request summary's `0 kW` is external grid demand, not total rover energy. The recorded approval acknowledges missing analyzed site hazard imagery even though a separate browse image is pinned.

## 3. Word-for-word narration

### 0:00–0:15

“An AI proposal is easy to write. The harder question is whether it becomes accountable work. This demonstration follows one recorded survey order through A.R.C., a mission-planning simulator using Mars as its first environment.”

### 0:15–0:35

“This is read-only inspection of an accelerated software study, not a new mission running now. The survey target is 175.15 metres. Its source describes a published rover record. The application preserves that citation and explicitly says: record, not typical performance.”

### 0:35–0:55

“Here, Muse Wonder requested an additional survey job using the create-job tool. The stored receipt contains the model, public tool arguments and provider response identifier. This is the director's concrete output, rather than a paragraph claiming that work happened.”

### 0:55–1:25

“Muse Spark then submitted the work order, naming the job, rover and evidence references. A separate assurance request approved it while acknowledging missing site obstacle analysis. That condition remains visible. Approval here means permission inside this configured simulator. It does not establish safe physical navigation, and the complete rover energy model remains unvalidated.”

### 1:25–1:50

“The work-order record separates the proposal from the simulator result. It records accepted validation, the input snapshot, calculation and completed outcome: 175.15 metres at tick 1976. These are simulated metres. Zero grid power means no draw from the outpost grid; it does not mean the rover uses no energy.”

### 1:50–2:15

“Each accepted decision retains the source versions it cited. I can move from the job into its input, calculation and result, then into the decision trail. That lets a reviewer examine the basis of the action instead of relying on the agent's summary alone.”

### 2:15–2:40

“This saved verification report records authenticated retrieval of 89 provider responses from the study. For the survey submission, it records matching response identity, model, token usage and public tool calls. This is evidence from the recorded run. It is not a fresh API call or independent access to an account's billing dashboard.”

### 2:40–3:00

“The demonstrated result is a traceable software workflow: a cited input, a Meta-generated work order, explicit authorization and a recorded simulator outcome. It gives a reviewer something concrete to inspect. It does not establish that the site is safe or that an autonomous colony is physically feasible.”

## 4. Evidence points

| Capability shown | Existing evidence | Proof shown on screen | Boundary |
|---|---|---|---|
| Inspect a sourced parameter | Acceptance snapshot, `spec.parameters.rover.max_drive_m_per_sol` | Value, quotation, source, locator and note in Records | Published record used as a scenario operating reference; not Arcadia measurement |
| Director creates bounded work | Stored Wonder response `resp_6aeb686dcea3768717514d9a` | Actual `create_job` arguments and ID in Agents | Recorded generation, not generation during filming |
| Specialist submits typed work | Spark `resp_6aeb69ae8dac53841e334690` | `submit_work_order` for `survey-extension-1`, `rover-1` and source IDs | Demonstrates the software tool path; no physical control |
| Assurance retains a condition | Spark `resp_6aeb69c60b1701040a524919`; D8 assurance | Acknowledged `no-site-imagery` and explicit limitation | Reviewer approval is policy authorization, not safety certification |
| Simulator records completion | Decision D8 and completed job in revision 2021 | `validation: accepted`, result at tick 1976, 175.15 m | Scenario calculation with incomplete terrain/whole-rover energy modeling |
| Decision/source traceability | D8 `source_versions`, input, calculation and outcome | Exact pinned IDs and decision trail | Hash linkage is not scientific validation of applicability |
| Provider-response correlation | `docs/live-responses-engine11.json` | 89/89 saved results and selected submission entry | No billing-dashboard assertion; no fresh authentication during recording |

Implementation: `mission/planner.py` typed tool loop; `mission/engine.py` validation/execution; `mission/store.py` persistence; `mission/inspection.py` projections; frontend `OperationsPanels.tsx` and the work-order drawer in `app/page.tsx`. Recording helper files are production utilities, not new product features.

Supporting report: `docs/live-mission-acceptance-engine11-final.json` records the extra survey over ticks 1952–1976. Its readiness result is **not** included as a demonstrated capability because the full mission depends on D21 water assumptions.

Supplementary verification during package production: `docs/submission-video/RESPONSE-CHECK-NOW.json` records four fresh authenticated GET requests for the selected director, plan, submission and assurance responses. All four returned HTTP 200 and matched identity, model, usage and public tool calls. No generation request was made. The video itself identifies the 89-response report as a saved report rather than claiming a fresh 89-request check.

## 5. Demonstration order validation

**Problem → one work order → cited input → director request → specialist submission → assurance condition → simulator outcome → source/decision chain → response correlation → conclusion.**

- One named job connects every shot; no tour of unrelated pages.
- Inputs precede agent actions, so source identifiers have meaning.
- The director creates work; the specialist submits it; assurance authorizes it; the deterministic engine records completion. These responsibilities are presented separately.
- The output follows authorization, preventing an agent statement from being mistaken for an execution result.
- Audit references follow the result; provider correlation follows the receipt it verifies.
- No benchmark, 3D motion or weather plot is added without a direct role in this demonstrated chain.

## 6. Hidden gap review — DO NOT DEMONSTRATE

| Excluded capability or claim | Reason |
|---|---|
| Fully autonomous colonization or full mission feasibility | Core engineering models and integrations are incomplete. A conditional readiness flag cannot establish feasibility. |
| Water startup validation or physical readiness | D21 extrapolates startup from a steady-state reference. Coupled thermal/fluid startup is incomplete. |
| Hive diagnosis, robotic repair, battery swapping and habitat offload | Generic procedure code exists, but the mission does not have the completed autonomous hardware/profile/manifest integration. |
| Certified rover routing or local obstacle avoidance | This work order explicitly acknowledges absent analyzed site imagery. Flat imagery and regional mapping do not qualify local traversability. |
| Complete rover energy or thermal realism | Reference mobility bookkeeping does not validate housekeeping, terrain loads or calibrated thermal performance. |
| Active robots moving in 3D | Scene layout/models/shuttling are illustrative; the selected mission is paused. Animation is not execution proof. |
| New SAM segmentation or a source refresh during filming | No new generation/refresh is part of this recording. Historical decoding/parsing is a different claim. |
| Current Arcadia weather or ground sensors | Local instruments are uninstrumented; off-site observations and climate models are different evidence classes. |
| Live replanning, live failures or live memory consolidation | This is a saved-run inspection. No newly exercised branch is asserted. |
| Private fork comparison | The selected acceptance viewer is read-only; final private-worker/package integration is outside this demonstrated workflow. |
| Reduced correlated error or autonomous superiority | Neither benefit is established by this demonstration or the bounded comparison results. |
| Production readiness, licensing clearance or deployed service reliability | No complete release acceptance, full license clearance or hosting reliability result is established. |
| Earth/Moon expansion, future humanoids or hardware control | Outside this Mars version or not delivered. |

If an excluded UI panel is visible during navigation, it is not narrated as working capability. Do not use its numbers, animation or status as proof. Include the selected order's actual open condition rather than hiding it.

## 7. Twenty skeptical judge questions

| # | Question | Defensible answer | Evidence |
|---|---|---|---|
| 1 | What exactly did this video prove? | Inspection of a recorded Meta-created/submitted survey order, authorization and simulator outcome. | D8, selected receipts and the complete job |
| 2 | Is a real rover controlled? | No. Execution advances persisted software state. | `mission/engine.py`; simulator label |
| 3 | What does Wonder do? | It requested the bounded survey extension and set its priority in the recorded study. | `create_job` receipt; director `set_mission_plan` receipt `resp_6aeb698faa3119a06cb54a8f` |
| 4 | What does Spark do? | It assessed work, estimated/submitted the survey and performed the separate assurance request. | Actual tool calls in Agents |
| 5 | Are these new calls during filming? | No. They are stored responses from the recorded acceptance run. | Read-only banner; recorded timestamps |
| 6 | How are fabricated receipts distinguished from provider evidence? | The saved comparison records authenticated GET retrieval and compares identity, model, usage and public calls. It is inspectable evidence, not billing access. | `live-responses-engine11.json` |
| 7 | Does this establish the owner's account billing? | No. That requires the owner's provider dashboard/account records. | Viewer disclaimer and verification scope |
| 8 | Why 175.15 metres? | The scenario uses a cited historical rover record as its work target; it is not typical or site-validated performance. | Parameter citation and D3 |
| 9 | Does zero kilowatts mean free movement? | No. It is zero external grid allocation; onboard mobility energy is a separate model. | Parameter note, reference battery model and job calculation |
| 10 | Was the route demonstrated safe? | No. Assurance retained missing site obstacle analysis. | D8 `no-site-imagery` condition |
| 11 | Can an agent declare the job complete? | The shown agent submitted work. The engine records the completed quantity/outcome. | Submission versus D8 outcome; `engine.py` |
| 12 | Does an assurance approval certify engineering safety? | No. It authorizes work within the declared scenario and retains its conditions. | Approval text and acknowledged condition |
| 13 | What is persistent? | This work order, decision, snapshot, result, source references and request receipts are retained in the recorded database. | Reopened UI and revision 2021 |
| 14 | Do the source hashes prove the model is correct? | No. They identify pinned evidence; applicability and model validity require additional review. | D8 version IDs and parameter interpretation |
| 15 | Is the energy model complete? | No. The record discloses incomplete total rover energy and local terrain characterization. | Specialist assessment and director summary |
| 16 | Did the entire mission reach physically valid readiness? | That is not demonstrated. The recorded readiness result is conditional on engineering assumptions, including D21. | Excluded full-mission result; package D21 |
| 17 | Are repair and offload operational here? | They are excluded. Configurable code is not completed mission integration. | Work service panel and procedure manifest absence |
| 18 | Are live forks shown? | No. This viewer prevents HTTP writes, and no worker is started for filming. | Acceptance-view button and read-only boundary |
| 19 | What does this add beyond a conversation? | A named tool-submitted work order is separately validated, authorized, executed in software and linked to retained inputs/results. | One complete D8 chain |
| 20 | What does it not prove? | Real-world colonization feasibility, safe navigation, complete physics, production readiness or superiority to another scheduler. | Scope disclosure, open condition and exclusion list |

## 8. Final demo risk review

| Reject this claim | Reason | Use this wording |
|---|---|---|
| “AI autonomously colonizes Mars.” | Complete physical mission capability is absent. | “Inspect a recorded agent-operated survey work order in a Mars mission simulator.” |
| “The mission proved readiness.” | Readiness depends on the partial conditional water model. | Omit the readiness claim from the video. |
| “Live Meta agents are working now.” | This recording inspects prior responses. | “These are recorded Wonder and Spark requests.” |
| “NASA says this rover will drive 175.15 metres here.” | A historical record is not a site prediction. | “The scenario uses a published record as its target.” |
| “Zero-power survey.” | Zero is grid allocation, not total energy. | “The job draws no outpost-grid power; onboard energy is modeled separately.” |
| “The route is cleared.” | The record explicitly retains absent obstacle analysis. | “The software authorization acknowledges missing site obstacle analysis.” |
| “Verified API calls from your account.” | Saved response matching is not direct account/billing access. | “The saved report records provider-response matching for these identifiers.” |
| “The source proves the engineering.” | Provenance and physical applicability are different. | “The decision preserves the exact evidence versions it cited.” |
| “Agents cannot make mistakes.” | Invalid proposals and modeling limits remain possible. | “Agents propose tools; deterministic validation controls state changes.” |
| “Ready for production.” | Final whole-product acceptance is absent. | Omit the production-readiness claim. |

### Recording acceptance

- Every narrated fact has a corresponding screen or exact supporting record.
- The read-only/recorded-study disclosure remains in the opening, captions and description.
- No new inference, physical sensing, dynamic mission execution or billing access is implied.
- The missing-obstacle condition and reference-performance limitation are spoken, not relegated to fine print.
- No API key, cookie, operator token, private reasoning or unrelated user data is visible.
- Total duration is 180 seconds; captions match the narration; speech and text remain readable.
- The published description identifies the study and evidence files. No publishing/upload action is authorized by this package.

### YouTube title

A.R.C. — From a Meta survey work order to an inspectable simulator result

### YouTube description

Three-minute proof-of-capability walkthrough of one recorded survey work order in A.R.C., a mission-planning simulator using Mars as its first environment. Shows a cited input, Wonder/Spark tool calls, explicit assurance conditions, simulator result and saved provider-response correlation.

This is read-only inspection of a recorded accelerated software study, not live inference or real robot control. The 175.15 m target uses a published rover record. Local obstacle clearance and complete rover energy modeling remain unvalidated. No colonization-feasibility, physical-readiness or production-readiness claim is made.

Evidence: mission `public`, revision 2021, tick 1976; decision D8; `live-mission-acceptance-engine11-final.json`; `live-responses-engine11.json`. Earlier MetroDesk deliberation/evidence patterns and existing Mars Council foundations are prior work; consult the contribution record for inherited versus new implementation. Attribution does not imply NASA or Meta endorsement.
