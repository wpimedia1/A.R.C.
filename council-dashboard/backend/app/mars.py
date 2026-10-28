"""Mars Industrial Colony Management simulator.

Facilities report state each tick; crisis scenarios inject shocks.
The council reads state, deliberates, and its chosen action feeds back
into the next tick. Small and deterministic: a demo vehicle, not a
physics engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Facility:
    name: str
    integrity: float  # 0..1
    output: float  # 0..1


@dataclass
class ColonyState:
    tick: int = 0
    facilities: Dict[str, Facility] = field(default_factory=dict)
    event_log: List[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{f.name}: integrity {f.integrity:.2f}, output {f.output:.2f}"
                 for f in self.facilities.values()]
        return f"tick {self.tick} | " + "; ".join(parts)


def new_colony() -> ColonyState:
    return ColonyState(facilities={
        "power": Facility("Power Grid", 0.92, 0.88),
        "water": Facility("Water Authority", 0.9, 0.85),
        "medical": Facility("Medical Center", 0.95, 0.9),
        "logistics": Facility("Logistics", 0.88, 0.82),
    })


SCENARIOS = {
    "reactor-failure": {
        "title": "Reactor Failure",
        "crisis": ("Primary reactor SCRAM at 02:14. Grid at 34% output. "
                   "Water purification needs full power within 6 hours or "
                   "contamination spreads. Habitat heating drains reserves."),
        "options": ["restart_reactor", "shed_load", "evacuate_sectors"],
        "experts": ["power_chief", "water_engineer", "medical_officer",
                    "logistics_coord", "agri_fab"],
        "irreversible": True,
        "shock": {"power": (0.34, 0.34)},
    },
    "water-contamination": {
        "title": "Water Contamination",
        "crisis": ("Perchlorate spike in sector 3 reservoir. Purification "
                   "at 61%. Medical reports first exposure cases. Grid "
                   "stable but purification draws surge power."),
        "options": ["isolate_sector", "surge_purify", "ration_water"],
        "experts": ["power_chief", "water_engineer", "medical_officer",
                    "logistics_coord", "agri_fab"],
        "irreversible": True,
        "shock": {"water": (0.55, 0.61)},
    },
    "habitat-breach": {
        "title": "Habitat Breach",
        "crisis": ("Micrometeorite breach in dome 2. Pressure falling 2% "
                   "per hour. 40 colonists in affected zone. Rovers ready, "
                   "medical on standby, sealing risks power reroute."),
        "options": ["seal_dome", "evacuate_dome", "patch_and_hold"],
        "experts": ["power_chief", "water_engineer", "medical_officer",
                    "logistics_coord", "agri_fab"],
        "irreversible": True,
        "shock": {"logistics": (0.7, 0.7)},
    },
}


def apply_shock(state: ColonyState, scenario: Dict) -> ColonyState:
    for fac, (integ, out) in scenario.get("shock", {}).items():
        if fac in state.facilities:
            state.facilities[fac].integrity = integ
            state.facilities[fac].output = out
    state.event_log.append(f"CRISIS: {scenario['title']}")
    return state


def apply_action(state: ColonyState, action: str) -> ColonyState:
    state.tick += 1
    bonus = 0.08
    for fac in state.facilities.values():
        fac.integrity = min(1.0, fac.integrity + bonus * 0.5)
        fac.output = min(1.0, fac.output + bonus * 0.4)
    state.event_log.append(f"ACTION: {action} -> stabilizing")
    return state
