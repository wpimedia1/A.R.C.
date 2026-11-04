# Water-model review — November 4, 2026

The completed real-agent mission **failed readiness**. Power, survey, drilling, trench and shielding completed; water remained held. The final assurance decision and director resolution are preserved in [live-acceptance-summary.json](live-acceptance-summary.json), with the provider IDs in its authentication reports.

## What the calculation currently does

The package uses a published 10 kW / 100 US gallon-per-day reference operating point and a unit conversion to energy per kilogram. Production consumes a finite scenario allocation and respects finite storage. Neither allocation is a measured deposit or a qualified tank. The code does not establish a melt pool or validate its startup and recirculation behavior before applying the steady-state calculation.

## Published evidence found

[NASA NTRS 20180007948, *Simulated Water Well Performance on Mars*](https://ntrs.nasa.gov/api/citations/20180007948/downloads/20180007948.pdf):

- PDF page 6 describes establishing a liquid-water reserve before pumping. This supports a separate establishment requirement; it supplies no universal startup time for this app's selected system.
- PDF page 8, Table 1 provides a 4,771.2 kg initial configuration estimate, including a 3,207 kg rover chassis. This is a specific alternative architecture, not the mass of the configured RedWater design.
- PDF page 10 compares provisional operating points under different environmental parameters. These are conditional model results; they do not qualify this hypothetical site's yield.

Raw PDF SHA-256: `ebee103ee0c190d0ed6e90616b47b70b5bfb15d05029541c11447e8d8d6d6af3`. The actual download contains 14 pages and 1,670,138 bytes. [Retrieval and review adoption](rodwell-reference-review.json) records its source version and time. The new reference is visible in the paused review mission's Records. The 159 previously authenticated responses retain their original pinned evidence; this paper has not been retroactively inserted into them.

## Remaining implementation

- Model establishment, melt inventory and recirculation separately from steady withdrawal. Require explicit source-backed or openly approved design inputs for starting water, geometry, heat transfer and pressure control.
- Use an internally consistent selected hardware architecture. Keep concept estimates, tested subsystem performance and actual local measurements distinct.
- Carry the site-resource hypothesis and uncertainty into the calculated outcome. SWIM consistency cannot supply a measured ice concentration or guaranteed recoverable volume.
- Test loss of heat, interrupted startup, limited feed, storage limits and restart recovery, then repeat real-agent readiness and post-readiness acceptance.

The existing hold remains evidence of an unfinished integrated water model. A prompt change that simply encourages approval would not supply that model. Published reference data exists; its architecture-specific integration remains work.
