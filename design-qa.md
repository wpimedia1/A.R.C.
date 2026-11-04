# Interface verification — November 4, 2026

Verified with Playwright/Edge on the real localhost API and a restored PostgreSQL review database. Ordinary view/interaction checks used no route interception, mock API, paid model calls or generated mission observations. A separate failure check deliberately aborted only the localhost ground-image request to verify the explicit failure message; it supplied no replacement response. The mission remained paused; its private benchmark fork executed 24 queued steps through the actual store/engine.

| Check | Observed result |
|---|---|
| Seven navigation views | All navigable at desktop/mobile sizes; zero captured page exceptions |
| Automated WCAG A/AA scan | Zero reported violations in fourteen runs; not accessibility certification |
| Mobile width | No document overflow at 390 px after migration-hash wrapping repair |
| Objective | Briefing, authorized work, blocker and latest recorded decision precede the scene |
| Scene | Separate outpost/rover cameras; viewing light explicitly labeled display-only |
| Execution truth | Paused/stale-worker state stops work depiction; stale DSN is not called current |
| Work-order keyboard access | Focus trapped, Escape closes, focus restores to invoking row |
| Private experiment | UI-created; explicit benchmark; setting persisted; 24 steps executed; matched interval; public review revision unchanged |
| Evidence image | Actual pinned SWIM PNG and site-covering HiRISE image served with matching hashes/version headers; wrong-site/proxy sources rejected |

Evidence: `docs/local-verification.json`, `output/playwright/browser-review.json`, `output/playwright/interactions-review.json` and screenshots in `output/playwright/` (ignored by Git).

Still open: newcomer usability review; screen-reader/manual testing; owner audio verification; richer equipment models and fine-scale work-site routing; full readiness/post-readiness and long-duration fault workflows. The scene is illustrative, not a validated physical reconstruction. No claim that the owner has accepted the entire original visual quality target.

The large dark blocks were traced to an annotated HiRISE browse product repeated across the plane. Rendering now uses one unannotated, hash-checked site window (1,600 m across), with PDS projection/dimension checks and no texture repetition. Final browser/source checks passed and the corrected screenshot was visually inspected. The approximately 4.51 m/pixel browse image is flat and coarse; equipment models and layout remain illustrative. This does not establish the original visual-quality target or a physical reconstruction.

The separate Windows-hosted real acceptance view on port 8022 also passed fourteen desktop/mobile automated view checks, with zero captured page errors, zero detected WCAG violations and no overflow. Its Create an experiment button is disabled and actual POST returned HTTP 403. It uses the calculated pinned experiment clock, not a claim of new local observations.

Final outcome inspection: the actual water assurance hold is visible on Today, exactly 71 API receipts appear separately from council summary cards, all 45 acceptance source pins resolve, and the write boundary returns 403. See final_outcome in local-verification.json.
