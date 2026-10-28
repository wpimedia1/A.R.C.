# Design QA — local test build

Source visual truth: `C:/Users/crudo/.codex/generated_images/01a18005-2b21-7083-b56c-efc4d22e432f/exec-9f1c4be6-489b-4653-986a-ea56c5716339.png` (selected Sol Briefing design 3).

Implementation: `docs/screenshots/desktop-final.png`; responsive evidence: `docs/screenshots/mobile-final.png`. URL: http://127.0.0.1:8020.

Viewport: desktop 1440 × 1000 CSS px, full-page capture 1440 × 1172; mobile 390 × 844 CSS px, full-page capture 390 × 1650. Source image 1487 × 1058. Compared at proportional display scale in one tool result, not as a pixel-aligned overlay. Source is illustrative sol 42; implementation is persisted public sol 0.08. Content differences from mission state are expected.

## Findings

- **P1, unfinished asset fidelity:** The source shows detailed realistic Mars equipment and terrain; the implementation renders procedural schematic primitives. State-driven behavior works, but the visual target is not met. Replace equipment with attributed production-quality 3D assets, improve materials and lighting, and preserve state-driven construction stages. Do not substitute a static successful-outpost image for operational state.
- **P2, layout and typography fidelity:** The source uses a heavier serif headline and larger right-hand briefing text with the scene higher on the page. The implementation uses lighter Libre Caslon Display and a larger intro region. Reduce intro height and increase briefing text size/weight before submission, then compare again at the same viewport.
- **P3, responsive readiness:** The compact layout hides the readiness counter, although all six status buttons remain visible. Add a compact explicit count for easier scanning.

## Required surfaces

- Fonts: serif/sans hierarchy is clear, but headline weight and small briefing text differ from the source.
- Spacing: desktop grid, six milestones and metrics remain legible; vertical density differs as described above. Mobile stacks without persistent-control overflow.
- Colors: warm paper, rust actions and muted green status are consistent with the reference direction. The rendered scene is less richly textured.
- Image quality: interactive schematic is sharp and responsive, but does not meet source asset fidelity.
- Copy: persisted activity, explicit assumptions and plain-language requirements replace illustrative source numbers. Completion text now correctly describes readiness; no fabricated mission outcomes are shown.

## Comparison history

1. Earlier completed-experiment comparison identified incorrect next-milestone copy and undersized equipment. Fixed completion copy and camera distance.
2. Mobile browser capture found oversized distance-scaled labels overlapping equipment. Removed distance scaling on desktop and hid overlay labels below 720 px; accessible work buttons and Outpost equipment list remain available. Revised mobile capture confirms unobstructed scene and controls.
3. Final reference and desktop capture were displayed together in one comparison input. Remaining asset and typography/layout mismatches are listed above. Focused image crops were unnecessary because full-view comparison clearly exposes these differences.

## Interaction evidence

Opened private experiment, ran one sol, observed six completed milestones and 125 kg water, opened readiness work order and pinned evidence, returned to public mission. Console error check returned none. Temporary responsive viewport overrides were reset after capture.

## Implementation checklist

- Complete 3D asset/material pass.
- Align headline weight, briefing typography and intro height.
- Add mobile readiness summary.
- Repeat matched-state visual comparison and independent newcomer usability test.

final result: blocked

This status concerns visual acceptance, not local runtime availability. Functional verification is recorded in `docs/LOCAL-VERIFICATION.md`.
