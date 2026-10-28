"""Council agents: anchor roles, domain experts, and the model client.

Every reasoning call goes through ModelClient with two tiers, both on
the Meta Model API by default: experts on OPEN_MODEL (muse-spark-1.3),
anchors on SMART_MODEL (muse-spark-1.3). The SMART tier inherits OPEN
credentials when its own are unset. Without credentials the call raises
with remediation, unless COUNCIL_OFFLINE=1 enables the seeded
deterministic fallback, which every payload labels as rehearsal.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx

def _env(*names: str, default: str = "") -> str:
    """First non-empty value wins, so blank .env lines inherit properly."""
    for name in names:
        val = os.environ.get(name, "")
        if val:
            return val
    return default


def _src(*names: str, inherited: str = "", missing: str = "(missing)") -> str:
    """Name which env var actually supplied the value (never the value)."""
    for name in names:
        if os.environ.get(name, ""):
            return name
    return inherited or missing


def _hint(key: str) -> str:
    """Non-sensitive key identifier: prefix, suffix, and length only."""
    if not key:
        return "(empty)"
    return f"{key[:3]}…{key[-2:]} (len {len(key)})"


OPEN_MODEL = _env("OPEN_MODEL", "MODEL_NAME", default="muse-spark-1.3")
OPEN_BASE_URL = _env("OPEN_BASE_URL", "MODEL_BASE_URL",
                     default="https://api.meta.ai/v1")
OPEN_API_KEY = _env("OPEN_API_KEY", "MODEL_API_KEY")
SMART_MODEL = _env("SMART_MODEL", default="muse-spark-1.3")
SMART_BASE_URL = _env("SMART_BASE_URL", "MODEL_BASE_URL",
                      default=OPEN_BASE_URL)
SMART_API_KEY = _env("SMART_API_KEY", "MODEL_API_KEY",
                     default=OPEN_API_KEY)

OPEN_KEY_FROM = _src("OPEN_API_KEY", "MODEL_API_KEY")
SMART_KEY_FROM = _src("SMART_API_KEY", "MODEL_API_KEY",
                      inherited="OPEN_API_KEY (inherited)")
OPEN_KEY_HINT = _hint(OPEN_API_KEY)
SMART_KEY_HINT = _hint(SMART_API_KEY)

STRATEGIST = "strategist"
DEVILS_ADVOCATE = "devils_advocate"

DOMAIN_EXPERTS = {
    "power_chief": (
        "Power Grid Chief",
        "Owns reactor output, grid stability, and load shedding calls.",
    ),
    "water_engineer": (
        "Water Authority Engineer",
        "Owns purification, pressure, and contamination containment.",
    ),
    "medical_officer": (
        "Medical Center Officer",
        "Owns triage capacity and habitat health logistics. Advisory "
        "only: never diagnoses or prescribes.",
    ),
    "logistics_coord": (
        "Logistics & Mining Coordinator",
        "Owns heavy equipment, rovers, supply chains, habitat maintenance.",
    ),
    "agri_fab": (
        "Manufacturing & Agriculture Chief",
        "Owns hydroponics output and structural repair fabrication.",
    ),
}


@dataclass
class Agent:
    agent_id: str
    title: str
    brief: str
    credibility: float = 0.8
    anchor: bool = False


def build_roster(scenario_experts: List[str]) -> List[Agent]:
    roster = [
        Agent(
            STRATEGIST,
            "The Strategist",
            "Long-horizon impacts, secondary and tertiary consequences, "
            "systemic risk. Votes against short-term fixes that create "
            "larger downstream failures.",
            credibility=0.9,
            anchor=True,
        ),
        Agent(
            DEVILS_ADVOCATE,
            "The Devil's Advocate",
            "Adversarial by design. Attacks majority assumptions, hunts "
            "'sounds right, is wrong' fallacies, defends discarded options.",
            credibility=0.85,
            anchor=True,
        ),
    ]
    for key in scenario_experts:
        title, brief = DOMAIN_EXPERTS[key]
        roster.append(Agent(key, title, brief, credibility=0.8))
    return roster


POSITION_SYSTEM = (
    "You are {title}. {brief}\n"
    "Crisis: {crisis}\nOptions: {options}\n"
    "Reply with JSON only: {{\"scores\": {{\"<option>\": [low, high]}}, "
    "\"rationale\": \"<one sentence>\"}}. "
    "low/high are 0..1 confidence bands; wider bands mean more hesitation."
)

COUNTER_SYSTEM = (
    "You are {title}. {brief}\n"
    "Crisis: {crisis}\nYour position: {mine}\nRival position: {theirs}\n"
    "Reply with JSON only: {{\"target\": \"<agent>\", "
    "\"contradiction\": \"<one sentence>\"}}."
)


@dataclass
class Position:
    agent_id: str
    scores: Dict[str, List[float]]
    rationale: str
    live_model: bool = False
    model: str = ""


CREDITS_HINT = ("set OPEN_BASE_URL + OPEN_API_KEY (claim the $150 Meta "
               "Model API credit); blank SMART_* inherits OPEN_*, or run "
               "with COUNCIL_OFFLINE=1 for rehearsal mode")


def offline() -> bool:
    return os.environ.get("COUNCIL_OFFLINE", "0") == "1"


def strip_fences(text: str) -> str:
    """Remove markdown code fences models wrap JSON replies in."""
    out = text.strip()
    if out.startswith("```"):
        out = out[3:]
        if out.lstrip().startswith("json"):
            out = out.lstrip()[4:]
        out = out.strip()
        if out.endswith("```"):
            out = out[:-3].strip()
    return out


class ModelClient:
    """Tiered inference: open weights for experts, Muse Spark for anchors.

    Live calls are the default and only production path. Failures raise
    with remediation unless COUNCIL_OFFLINE=1 explicitly enables the
    seeded deterministic fallback for rehearsal.
    """

    def __init__(self, seed: int = 7) -> None:
        self.seed = seed

    def _tier(self, tier: str):
        if tier == "smart":
            return SMART_MODEL, SMART_BASE_URL, SMART_API_KEY
        return OPEN_MODEL, OPEN_BASE_URL, OPEN_API_KEY

    def _post(self, tier: str, messages: List[Dict[str, str]],
              temperature: float, label: str = "") -> Dict[str, Any]:
        import json as _json
        model, base, key = self._tier(tier)
        print(f"[council] live call -> {tier}:{model} {label}", flush=True)
        resp = httpx.post(
            base.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": messages,
                  "temperature": temperature},
            timeout=30.0,
        )
        resp.raise_for_status()
        print(f"[council] live call <- {tier}:{model} {label}", flush=True)
        content = resp.json()["choices"][0]["message"]["content"]
        try:
            return _json.loads(strip_fences(content)), model
        except Exception:
            raise RuntimeError(
                f"{tier} tier returned non-JSON; preview: {content[:200]}")

    def _fallback_scores(
        self, agent: Agent, options: List[str], crisis: str
    ) -> Dict[str, List[float]]:
        h = int(hashlib.sha256(
            f"{self.seed}|{agent.agent_id}|{crisis}".encode()
        ).hexdigest(), 16)
        # Rehearsal ladder: midpoints spread wide on purpose so the
        # trigger always sees genuine ambiguity (2+ paths over 0.5) and
        # hesitation above threshold. Deterministic per seed.
        ladder = (0.30, 0.55, 0.75, 0.45, 0.65)
        out = {}
        for i, opt in enumerate(options):
            jitter = (((h >> (8 * i)) % 5) - 2) / 100.0
            mid = ladder[i % len(ladder)] + jitter
            if agent.anchor and agent.agent_id == DEVILS_ADVOCATE:
                mid = 1.0 - mid  # dissent by construction
            half = 0.20 + (((h >> (8 * i + 4)) % 16) / 100.0)
            out[opt] = [round(max(0.0, mid - half), 3),
                        round(min(1.0, mid + half), 3)]
        return out

    def position(
        self, agent: Agent, crisis: str, options: List[str],
        tier: str = "open",
    ) -> Position:
        model, base, key = self._tier(tier)
        if base and key:
            try:
                data, used = self._post(tier, [
                    {"role": "system", "content": "Reply with JSON only."},
                    {"role": "user", "content": POSITION_SYSTEM.format(
                        title=agent.title, brief=agent.brief,
                        crisis=crisis, options=", ".join(options))},
                ], 0.4, label=f"position:{agent.agent_id}")
                if "scores" not in data:
                    raise RuntimeError(
                        f"{tier} tier returned no scores; keys: "
                        f"{sorted(data.keys())}")
                return Position(agent.agent_id, data["scores"],
                                data.get("rationale", ""), live_model=True,
                                model=used)
            except Exception as exc:
                if not offline():
                    raise RuntimeError(
                        f"{tier} tier call failed ({exc}); {CREDITS_HINT}")
        elif not offline():
            raise RuntimeError(
                f"{tier} tier unconfigured; {CREDITS_HINT}")
        return Position(
            agent.agent_id,
            self._fallback_scores(agent, options, crisis),
            "rehearsal fallback position (COUNCIL_OFFLINE=1)",
            live_model=False,
            model="fallback",
        )

    def counter(
        self, agent: Agent, crisis: str, mine: str, theirs: str, target: str,
        tier: str = "open",
    ) -> Dict[str, str]:
        model, base, key = self._tier(tier)
        if base and key:
            try:
                data, used = self._post(tier, [
                    {"role": "system", "content": "Reply with JSON only."},
                    {"role": "user", "content": COUNTER_SYSTEM.format(
                        title=agent.title, brief=agent.brief,
                        crisis=crisis, mine=mine, theirs=theirs)},
                ], 0.6, label=f"counter:{agent.agent_id}->{target}")
                data["model"] = used
                data["live_model"] = True
                return data
            except Exception as exc:
                if not offline():
                    raise RuntimeError(
                        f"{tier} tier call failed ({exc}); {CREDITS_HINT}")
        elif not offline():
            raise RuntimeError(
                f"{tier} tier unconfigured; {CREDITS_HINT}")
        return {"target": target,
                "contradiction": "rehearsal fallback counter-argument",
                "model": "fallback", "live_model": False}
