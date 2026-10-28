"""Trigger engine and the strict 3-round council pipeline."""
from __future__ import annotations

import asyncio
import concurrent.futures as cfuts
import os
from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from . import events as E
from .agents import (
    DEVILS_ADVOCATE,
    Agent,
    ModelClient,
    Position,
    build_roster,
)
from .ddpg import DDPGSteerer
from .ingest import ingest_all
from .maps import generate_situation_map
from .tools import ToolBench
from .wonder import UNCERTAINTY_BAR, predict_paths

from .fuzzy import (
    HesitantScore,
    competing_paths,
    parse_scores,
    uncertainty,
)
from .mars import apply_action, apply_shock, new_colony
from .trust import (
    fuse,
    kmeans,
    preference_vectors,
    silhouette,
    similarity_matrix,
    trust_matrix,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

UNCERTAINTY_THRESHOLD = float(os.environ.get("UNCERTAINTY_THRESHOLD", "0.35"))
CONSENSUS_THRESHOLD = float(os.environ.get("CONSENSUS_THRESHOLD", "0.9"))


def ring_topology(n: int) -> np.ndarray:
    topo = np.zeros((n, n))
    for i in range(n):
        topo[i, (i + 1) % n] = 1.0
        topo[i, (i - 1) % n] = 0.5
    return topo


def consensus_level(positions: Dict[str, Dict[str, HesitantScore]]) -> float:
    mids = np.array([[s.midpoint for s in p.values()] for p in positions.values()])
    return float(1.0 - mids.std(axis=0).mean())


@dataclass
class CouncilResult:
    mode: str
    action: str
    consensus: float
    dissent_log: List[Dict]
    clusters: List[int]
    silhouette: float
    steering: List[float]
    live_model: bool
    map_artifact: str = ""
    wonder_paths: List[Dict] = None


def _ask_position(job) -> tuple:
    """Round 1 worker: runs in a separate process for true isolation."""
    (agent_id, title, brief, credibility, anchor, crisis, options, tier,
     seed) = job
    from .agents import Agent, ModelClient
    print(f"[council] worker {agent_id} ({tier}) starting", flush=True)
    agent = Agent(agent_id, title, brief, credibility, anchor)
    pos = ModelClient(seed=seed).position(agent, crisis, options, tier=tier)
    print(f"[council] worker {agent_id} done live={pos.live_model}",
          flush=True)
    return (agent_id, {"scores": pos.scores, "rationale": pos.rationale,
                       "live_model": pos.live_model, "model": pos.model})


async def run_devil_check(scenario: Dict, seed: int = 7,
                          bus: E.EventBus | None = None) -> CouncilResult:
    """Standalone adversarial pre-flight check: the Devil's Advocate alone."""
    bus = bus or E.EventBus()
    client = ModelClient(seed=seed)
    options: List[str] = scenario["options"]
    await bus.publish(E.Event(
        E.RUN_STARTED,
        payload={"scenario": scenario["title"], "mode": "devil-check"},
    ))
    devil = Agent(
        DEVILS_ADVOCATE, "The Devil's Advocate",
        "Adversarial by design. Attacks majority assumptions, hunts "
        "'sounds right, is wrong' fallacies, defends discarded options.",
        credibility=0.85, anchor=True,
    )
    pos = client.position(devil, scenario["crisis"], options, tier="smart")
    scores = parse_scores(pos.scores)
    objections = []
    for opt in options:
        reply = client.counter(devil, scenario["crisis"], opt, opt,
                               "consensus", tier="smart")
        objections.append({"option": opt,
                           "objection": reply.get("contradiction", "")})
    best = max(scores.items(), key=lambda kv: kv[1].midpoint)[0]
    verdict = {"agent": DEVILS_ADVOCATE, "preferred": best,
               "objections": objections,
               "live_model": pos.live_model, "model": pos.model}
    await bus.publish(E.Event(E.DEVIL_VERDICT, agent_id=DEVILS_ADVOCATE,
                              payload=verdict))
    await bus.publish(E.Event(
        E.RUN_FINISHED, payload={"action": best, "mode": "devil"}))
    return CouncilResult("devil", best, 1.0, [verdict], [], 0.0, [],
                         pos.live_model)


async def run_council(
    scenario: Dict, seed: int = 7, bus: E.EventBus | None = None,
    scenario_key: str = "custom", audio_path: str | None = None,
    image_path: str | None = None, force_council: bool = False,
) -> CouncilResult:
    bus = bus or E.EventBus()
    client = ModelClient(seed=seed)
    state = apply_shock(new_colony(), scenario)
    options: List[str] = scenario["options"]
    roster = build_roster(scenario["experts"])
    by_id = {a.agent_id: a for a in roster}

    await bus.publish(E.Event(
        E.RUN_STARTED,
        payload={"scenario": scenario["title"], "state": state.summary()},
    ))

    # Multimodal ingestion through the self-repairing tool bench.
    bench = ToolBench()
    bench.register(
        "telemetry",
        lambda: ingest_all(scenario["title"], scenario["crisis"],
                           audio_path, None)["telemetry"])
    bench.register(
        "segmentation",
        lambda: ingest_all(scenario["title"], scenario["crisis"],
                           None, image_path)["damage"])
    tele_rep = bench.call("telemetry")
    seg_rep = bench.call("segmentation")
    for rep in (tele_rep, seg_rep):
        if not rep.ok or rep.diagnostic_output:
            await bus.publish(E.Event(
                E.TOOL_REPAIRED,
                payload={"tool": rep.tool, "ok": rep.ok,
                         "attempts": rep.attempts,
                         "diagnostic": rep.diagnostic_output,
                         "error": rep.error,
                         "duration_s": rep.duration_s},
            ))
    telemetry = tele_rep.result or {}
    damage = seg_rep.result or {}
    zones = damage.get("zones", [])
    await bus.publish(E.Event(E.AUDIO_INGESTED, payload={
        "count": len(telemetry.get("telemetry", [])),
        "live_model": telemetry.get("live_model", False)}))
    await bus.publish(E.Event(E.DAMAGE_ZONES, payload={
        "zones": zones, "live_model": damage.get("live_model", False)}))

    def crisis_for(agent_id: str) -> str:
        if agent_id in ("logistics_coord", "medical_officer") and zones:
            coords = "; ".join(
                f'{z["id"]} {z["type"]} bbox {z.get("bbox")}' for z in zones)
            return scenario["crisis"] + f" Damage zones: {coords}."
        return scenario["crisis"]

    # Pre-execution trigger: quick solo probe first (anchor tier).
    probe = client.position(roster[0], scenario["crisis"], options,
                            tier="smart")
    probe_scores = parse_scores(probe.scores)
    paths = competing_paths(probe_scores)
    unc = uncertainty(probe_scores)
    irreversible = bool(scenario.get("irreversible", False))
    # Replay runs are full-pipeline demonstrations: they always convene
    # the council. Routine/custom runs still go through the trigger below.
    full_council = (
        force_council or
        (paths >= 2 and unc > UNCERTAINTY_THRESHOLD and irreversible)
    )
    devil_check = (not full_council and irreversible
                   and (paths >= 2 or unc > UNCERTAINTY_THRESHOLD))
    mode = "council" if full_council else ("devil" if devil_check
                                           else "single")
    await bus.publish(E.Event(
        E.MODE_SELECTED,
        payload={"mode": mode,
                 "competing_paths": paths, "uncertainty": round(unc, 3),
                 "irreversible": irreversible,
                 "forced": bool(force_council and full_council)},
    ))
    if devil_check:
        return await run_devil_check(scenario, seed, bus)
    if not full_council:
        best = max(probe_scores.items(), key=lambda kv: kv[1].midpoint)[0]
        apply_action(state, best)
        await bus.publish(E.Event(
            E.RUN_FINISHED, payload={"action": best, "mode": "single"}))
        return CouncilResult("single", best, 1.0, [], [], 0.0, [],
                             probe.live_model)

    # Round 1: isolated position formation. Each worker gets only its
    # own brief and returns only its own position: zero cross-influence
    # by construction. Threads (not processes) because Windows process
    # spawn plus a torch import per worker hangs real machines; the
    # network-bound Meta calls release the GIL, so all 7 live calls
    # still go out concurrently. The gather has a hard timeout so a
    # stuck worker fails loudly instead of stalling the dashboard.
    await bus.publish(E.Event(E.EVENT_START_ROUND_1))
    jobs = [(a.agent_id, a.title, a.brief, a.credibility, a.anchor,
             crisis_for(a.agent_id), options,
             "smart" if a.anchor else "open", seed)
            for a in roster]
    print(f"[council] round 1: {len(jobs)} isolated workers starting",
          flush=True)
    with cfuts.ThreadPoolExecutor(
            max_workers=min(3, len(jobs))) as pool:
        loop = asyncio.get_running_loop()
        try:
            asked = await asyncio.wait_for(asyncio.gather(*[
                loop.run_in_executor(pool, _ask_position, job)
                for job in jobs
            ]), timeout=600.0)
        except asyncio.TimeoutError:
            pool.shutdown(wait=False, cancel_futures=True)
            raise RuntimeError(
                "Round 1 workers timed out after 600s; "
                "check the server window for per-call progress")
    print("[council] round 1: all workers returned", flush=True)
    raw_positions: Dict[str, Position] = {}
    for agent_id, payload in asked:
        pos = Position(agent_id, payload["scores"], payload["rationale"],
                       payload["live_model"], payload["model"])
        raw_positions[agent_id] = pos
        await bus.publish(E.Event(
            E.ROUND_1_SUBMIT, agent_id=agent_id,
            payload={"scores": pos.scores, "rationale": pos.rationale,
                     "live_model": pos.live_model, "model": pos.model},
        ))
    positions = {aid: parse_scores(p.scores)
                 for aid, p in raw_positions.items()}

    # Round 2: trust-similarity fusion, clustering, cross-examination.
    await bus.publish(E.Event(E.EVENT_START_ROUND_2))
    ids, pref = preference_vectors(positions, options)
    sim = similarity_matrix(pref)
    cred = [by_id[aid].credibility for aid in ids]
    trust = trust_matrix(ring_topology(len(ids)), cred)
    rel = fuse(sim, trust)
    labels, _ = kmeans(rel, k=2, seed=seed)
    sil = silhouette(rel, labels.tolist())
    await bus.publish(E.Event(
        E.CLUSTER_FORMED,
        payload={"agents": ids, "labels": [int(v) for v in labels],
                 "silhouette": round(sil, 3)},
    ))
    mean_unc = float(np.mean([uncertainty(p) for p in positions.values()]))
    print(f"[council] mean uncertainty {mean_unc:.3f}", flush=True)
    if mean_unc > UNCERTAINTY_BAR:
        print("[council] wonder paths predicting", flush=True)
        wonder_out = predict_paths(scenario["crisis"], options, mean_unc)
    else:
        wonder_out = {"paths": [], "wonder_live": False,
                      "note": "uncertainty below bar; no paths predicted"}
    await bus.publish(E.Event(E.WONDER_PATHS, payload=wonder_out))
    for agent in roster:
        print(f"[council] round 2 cross-exam: {agent.agent_id}", flush=True)
        rivals = [r for r in roster if r.agent_id != agent.agent_id]
        rival = max(
            rivals,
            key=lambda r: abs(
                positions[r.agent_id][options[0]].midpoint
                - positions[agent.agent_id][options[0]].midpoint
            ),
        )
        mine = options[0]
        reply = client.counter(
            agent, scenario["crisis"], mine, mine, rival.agent_id,
            tier="smart" if agent.anchor else "open")
        await bus.publish(E.Event(
            E.COUNTERARGUE, agent_id=agent.agent_id, payload=reply))

    # Round 3: DDPG steering toward the consensus threshold.
    await bus.publish(E.Event(E.EVENT_START_ROUND_3))
    steer = DDPGSteerer(seed=seed)
    steering: List[float] = []
    original = {aid: {o: s.midpoint for o, s in p.items()}
                for aid, p in positions.items()}
    consensus = consensus_level(positions)
    for step in range(12):
        if consensus >= CONSENSUS_THRESHOLD:
            break
        devs = {aid: float(np.mean([
            abs(s.midpoint - np.mean([positions[o2][o].midpoint
                                      for o2 in positions]))
            for o, s in p.items()]))
            for aid, p in positions.items()}
        worst = max(devs, key=devs.get)
        mean_vec = {o: float(np.mean([positions[a][o].midpoint
                                      for a in positions]))
                    for o in options}
        state_vec = np.array([
            consensus,
            float(np.mean(list(devs.values()))),
            float(max(devs.values())),
            steering[-1] if steering else 0.0,
        ])
        intensity = steer.act(state_vec)
        steering.append(round(intensity, 3))
        prev_consensus = consensus
        before = {o: positions[worst][o].midpoint for o in options}
        for o in options:
            s = positions[worst][o]
            target = mean_vec[o]
            new_mid = s.midpoint + intensity * 0.25 * (target - s.midpoint)
            half = s.hesitation / 2.0
            positions[worst][o] = HesitantScore(new_mid - half, new_mid + half)
        consensus = consensus_level(positions)
        shift = float(np.mean([abs(positions[worst][o].midpoint - before[o])
                               for o in options]))
        r = steer.reward(prev_consensus, consensus, shift, step=step,
                         max_steps=12)
        all_dev = [
            abs(positions[a][o].midpoint - float(np.mean(
                [positions[b][o].midpoint for b in positions])))
            for a in positions for o in options
        ]
        next_vec = np.array([
            consensus,
            float(np.mean(all_dev)),
            float(max(all_dev)),
            intensity,
        ])
        steer.observe(state_vec, intensity, r, next_vec)
        await bus.publish(E.Event(
            E.STEER_APPLIED,
            payload={"step": step, "agent": worst,
                     "intensity": round(intensity, 3),
                     "consensus": round(consensus, 3),
                     "reward": round(r, 4)},
        ))

    totals = {o: float(np.mean([positions[a][o].midpoint for a in positions]))
              for o in options}
    action = max(totals, key=totals.get)
    for aid, p in positions.items():
        await bus.publish(E.Event(
            E.VOTE_CAST, agent_id=aid,
            payload={"scores": {o: [s.low, s.high] for o, s in p.items()}}))
    await bus.publish(E.Event(
        E.CONSENSUS_REACHED,
        payload={"action": action, "consensus": round(consensus, 3)}))
    map_path = os.path.join(DATA_DIR, f"map_{scenario_key}.svg")
    print("[council] situation map generating", flush=True)
    map_out = generate_situation_map(scenario["title"], action, zones,
                                     map_path)
    await bus.publish(E.Event(
        E.MAP_GENERATED,
        payload={"map": map_out["map"],
                 "live_model": map_out["live_model"],
                 "note": map_out.get("note", "")}))

    # Dissent log: whoever moved most, plus the Devil's Advocate record.
    movement = {
        aid: float(np.mean([abs(positions[aid][o].midpoint - original[aid][o])
                             for o in options]))
        for aid in positions
    }
    dissenters = sorted(movement, key=movement.get, reverse=True)[:2]
    if DEVILS_ADVOCATE not in dissenters:
        dissenters.append(DEVILS_ADVOCATE)
    dissent_log = [
        {"agent": aid,
         "original": {o: round(v, 3) for o, v in original[aid].items()},
         "final": {o: round(positions[aid][o].midpoint, 3) for o in options},
         "moved": round(movement[aid], 3)}
        for aid in dissenters
    ]
    for entry in dissent_log:
        await bus.publish(E.Event(E.DISSENT_LOGGED, agent_id=entry["agent"],
                                  payload=entry))
    apply_action(state, action)
    await bus.publish(E.Event(
        E.RUN_FINISHED,
        payload={"action": action, "mode": "council",
                 "state": state.summary()},
    ))
    live = any(p.live_model for p in raw_positions.values())
    return CouncilResult("council", action, consensus, dissent_log,
                         [int(v) for v in labels], sil, steering, live,
                         map_artifact=map_out["map"],
                         wonder_paths=wonder_out.get("paths", []))
