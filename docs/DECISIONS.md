# Mission decisions, conflicts and known limits

Package: `council-dashboard/backend/mission/packages/arcadia-mars-v1.json`
Validate and print every value: `python -m mission.package` (run from `council-dashboard/backend`).

Every number used by the mission is either **published** (source, page/slide, quoted sentence, retrieval date), **derived** (formula over other parameters, recomputed at load) or **computed** (IAPWS R10-06 / IAPWS-95 water and ice properties via the `iapws` package). The mission refuses to start while any operator decision below is unapproved.

## Operator decisions

| ID | Decision | Status |
|---|---|---|
| D1 | Water from Arcadia excess ice by Rodwell melt extraction, at the Hoffman et al. (2016) operating point: ~10 kW sustains 100 US gal/day → 0.634 kWh per kg water | Approved 2026-10-31 |
| D2 | Two RASSOR-class excavators (M-WIP Case D2), used for habitat trench and regolith shielding | Approved 2026-10-30 |
| D3 | One survey batch = one sol of driving at the published record distance (175.15 m) | Approved 2026-10-30 |
| D4 | The 90 t Common Habitat is assumed already landed beside its trench. **Offloading from the lander is not modeled**: Howard et al. (2023) give no offload time or power, and the baseline crane concept is not represented in the simulator. Readiness therefore excludes habitat offload. | Approved 2026-10-30 — disclosed limitation |
| D5 | Costs use Perseverance historical figures: $2.4 B build+launch / 1,025 kg → $2.34 M per landed kg; $300 M prime operations / ~668.6 sols → $448,684 per operating sol. Nominal USD; source states no currency year. | Approved 2026-10-30 |
| D6 | No spending ceiling; spending is accounted only | Approved 2026-10-30 |
| D7 | One simulation tick = 1/24 sol (product pacing, not physics) | Approved 2026-10-30 |
| D8 | Fission power deployment is a job lasting 162 h: summed lunar deployment timeline from Oleson et al. 2022 (NASA/TM-20220012395, Table 3.6): offload 2 d, transport 1 d, control box 10 h, startup 8 h, commissioning 24 h, 1 km cable 2 d. No grid power until it completes. Lander and rover support are assumed present, not modeled as assets. | Approved 2026-10-31 |
| D9 | Rodwell establishment is a drilling job through 20 m of overburden at the lowest tested rate of penetration, 0.35 mm/s (Stolov et al. 2026, Table 4) = 15.9 h, requiring commissioned power. Drilling energy and melt start-up time are not published: drilling energy is recorded as **not estimated**. | Approved 2026-10-31 |
| D10 | The Meta agents run on Earth (every model request is made from Earth), so every agent work order is an uplink. It is held while Mars is within 2° of the Sun as seen from Earth (LASP 2015) and until DSN Now shows an active uplink to a spacecraft at Mars range (within the Mars sphere of influence, 577,269 km, derived from NSSDC GM and semimajor axis) since the previous tick; it arrives after the one-way light time (ERFA geometry, IAU au and c), rounded up to whole ticks. Equipment and power are reserved from authorization. If the DSN feed cannot be read, orders are not held by DSN and the order records it. The fixed-priority benchmark is onboard and not gated. Experiments freeze the environment at the fork point and apply no DSN data. Relay through Mars orbiters is assumed; orbiter pass timing over the outpost is not modeled. | Approved 2026-10-31 (owner instruction: live Mars conditions change the scenario) |
| D11 | Mars date, season (Ls) and local time come from the Mars24 algorithm at real UTC; the public mission runs in real Mars time (one tick every 1/24 sol). A change of season, the start or end of solar conjunction, and resuming after a pause trigger agent replanning. Dust and season apply no rate change: the outpost is fission-powered (NASA: "No worries about meeting power demands during the night or long, sunlight-reducing dust storms.") and no source publishes a dust or frost rate penalty for these machines. | Approved 2026-10-31 |
| D12 | A failed robot is replaced, not repaired (no published robotic repair procedure). The logistics and finance agent orders an identical unit; it launches at the next Earth–Mars Hohmann window (Mars leading Earth by 44.35°, ERFA positions) and arrives 258.9 days later (both derived from NSSDC constants). Cost = mass × landed cost per kg (D5); the Rodwell ships with cost not estimated. The fixed-priority benchmark orders automatically. | Approved 2026-10-31 (owner instruction) |
| D13 | At genesis the worker searches the USGS HiRISE footprint index for a HiRISE RED product whose footprint contains the mission site (40° N, 190° E) and runs SAM 3.1 on it. Only such detections route the survey (obstacle grid from boulder and crater boxes, 8-connected A*, survey drive × route/straight length). Otherwise SAM runs on the reference image ESP_052358_2210, labelled a proxy 524 km from the site, and the survey is unchanged. | Approved 2026-10-31; revised after audit 2026-10-31 |
| D14 | Rover and excavators fail at random while working: probability per tick 1 − exp(−λ·Δt), λ = 6.551e-4 /h, the series sum of the module failure rates in Stancliff, Dolan & Trebi-Ollennu (2005), Table 2. Deterministic draws per mission seed, tick and unit. The fission unit (10-year no-maintenance design) and the Rodwell (no published rate) do not fail. Failures stop work and trigger D12 replacement. | Approved 2026-10-31 (owner instruction) |
| D15 | A work order reaches the outpost at the first MRO relay opportunity after the light time: site LMST 15:03 (ascending node, NTRS 20080012690) or 03:03. Other relay orbiters are not modeled. | Approved 2026-10-31 (owner instruction) |
| D16 | Measured → estimated → checked. Measured: NASA's public daily weather summaries from Curiosity REMS (Gale) and Perseverance MEDA (Jezero), stored per sol, append-only, with source and date; the stations are far from Arcadia and labelled so. Estimated: for every sol between the newest measurement and today, plus 3 sols ahead, each variable is estimated from the station's own history: Ls climatology (±7.5°, widened to reach 10 samples) plus the newest anomaly decayed by the series' lag-1 autocorrelation, with a 95 % interval. Checked: when the measurement arrives, every estimate for that sol is marked confirmed (inside the interval) or corrected, with the error. The director agent receives all three and may order protective standby (1–72 ticks) only by citing the exact measurement or estimate. | Approved 2026-10-31 (owner instruction) |
| D17 | The mission starts only when a user presses Start (genesis); the API and worker never create it. After Start, the landing at the site is replayed on NASA's Mars 2020 EDL timeline (edl.* parameters, PIA24316–PIA24318): a replay of published values, not a physics simulation. Values shown as published at each event, interpolated and labelled between events; entry altitude and backshell time are not published and stay unknown. Conflict kept: the same caption gives parachute + ~20 s and "just under six minutes" for heat-shield separation; parachute + 20 s is used and both are shown. Cargo landers are unspecified by any source; the Mars 2020 profile is the reference for each. No Earth–Mars cruise is shown. | Approved 2026-11-01 (owner instruction) |

## Tracked conflicts

Both sides of every conflict are stored as parameters, validated at load, and reported by `python -m mission.package`.

1. **Regolith water-extraction power.** Kleinhenz & Paz (2017): 17 kW thermal at 1.36 kg/h → 12.5 kWh/kg. M-WIP (2016): ~8 kW for 16 t over 480 sols → 5.92 kWh/kg. No value selected; regolith extraction is not used for execution after D1.
2. **Ice extraction energy.** Thermodynamic minimum to warm 214 K ice and melt it: 0.124 kWh/kg. Minimum for sublimation capture: 0.818 kWh/kg. Hoffman (2016) modeled Rodwell operating point (includes heat lost to surrounding ice; assumes −80 °C ice): 0.634 kWh/kg. **Selected: Rodwell operating point**; the melt minimum is the physical lower bound.

## Correction to owner-supplied figures (2026-10-31)

The owner proposed 2.73–5.5 MJ/kg for Arcadia ice. Recomputed with IAPWS standards:
- Latent heat of sublimation at the triple point is **2,834 kJ/kg**, not 2,594 kJ/kg.
- Specific heat of ice falls with temperature (1.67 kJ/kg·K at 214 K), so warming 214 K → 273.15 K takes **111 kJ/kg**, not 132 kJ/kg.
- A Rodwell or pressurized melt process does not sublimate: minimum is 111 + 333 = **445 kJ/kg (0.124 kWh/kg)**.
- The 50–65 % efficiency attributed to Honeybee MISWE/RedWater could not be found in a published source and is **not used**. The Hoffman (2016) operating point is used instead.
- Bramson et al. (2015) support **up to 75 % ice by volume** in Arcadia, not 80–100 %.

## Known limits

- Ice temperature uses the NSSDC global mean surface temperature (214 K). Bramson (2015, p.8) states deep subsurface temperature equals the annual mean surface temperature; no Arcadia-specific value was found.
- Overburden up to 20 m (Mank et al. 2021) is drilled at 0.35 mm/s (D9); drilling energy is not published.
- The fission power unit (40 kWe) is a NASA lunar demonstration design applied to Mars.
- Source check (2026-10-31): 36 published quotes verified verbatim against the PDFs in `sources/` (`python -m mission.verify_sources`, report in `docs/source-verification.json`). Seven Kleinhenz/M-WIP quotes captured earlier by the web tool were paraphrases and were replaced with the documents' exact wording; no value changed. 12 values come from web pages or documents not in `sources/` (JPL quick facts, NASA blog, NSSDC fact sheet, NASA TP-3079, Mank 2021 abstract, ProofWiki) and remain unchecked against an original.
- RASSOR 2.0 "per day" is a 24 h period of 16 h mining and 8 h recharging (Mueller et al. 2016, p.3). The engine's 24 h average power (450 W) uses the same daily energy as 675 W over 16 h.
- `sources/` also holds `Fission Surface Power - NASA.pdf` and `Deep Fission - Executive Summary` (reviewed; not used: no parameter needed from them).
