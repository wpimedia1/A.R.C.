"""Focused contract tests (stdlib unittest; run: python -m unittest).

Not executed in the build sandbox (no Python runner there); run locally
after `pip install -r requirements.txt`.
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import events as E  # noqa: E402
from app.agents import strip_fences  # noqa: E402
from app.main import health  # noqa: E402
from app.council import run_council, run_devil_check  # noqa: E402
from app.ddpg import DDPGSteerer  # noqa: E402
from app.fuzzy import HesitantScore, competing_paths, uncertainty  # noqa: E402
from app.ingest import segment_damage, transcribe_dispatch_log  # noqa: E402
from app.mars import SCENARIOS  # noqa: E402
from app.wonder import predict_paths  # noqa: E402
from app.trust import (  # noqa: E402
    fuse,
    hamacher,
    kmeans,
    silhouette,
    similarity_matrix,
    trust_matrix,
)

import numpy as np  # noqa: E402


class FuzzyTest(unittest.TestCase):
    def test_hesitation_width(self):
        s = HesitantScore(0.2, 0.7)
        self.assertAlmostEqual(s.hesitation, 0.5)
        self.assertAlmostEqual(s.midpoint, 0.45)

    def test_clamps_and_orders(self):
        s = HesitantScore(0.9, 0.1)
        self.assertLessEqual(s.low, s.high)
        self.assertGreaterEqual(s.low, 0.0)
        self.assertLessEqual(s.high, 1.0)

    def test_uncertainty_and_paths(self):
        scores = {"a": HesitantScore(0.6, 0.8), "b": HesitantScore(0.1, 0.2)}
        self.assertAlmostEqual(uncertainty(scores), 0.15)
        self.assertEqual(competing_paths(scores), 1)


class TrustTest(unittest.TestCase):
    def test_hamacher_bounds(self):
        rng = np.random.default_rng(0)
        a = rng.random((4, 4))
        b = rng.random((4, 4))
        h = hamacher(a, b)
        self.assertTrue(bool(((h >= 0) & (h <= 1)).all()))

    def test_fuse_symmetric(self):
        rng = np.random.default_rng(1)
        x = rng.random((5, 3))
        sim = similarity_matrix(x)
        trust = trust_matrix(np.eye(5), [0.8] * 5)
        f = fuse(sim, trust)
        self.assertTrue(bool(np.allclose(f, f.T)))

    def test_kmeans_silhouette_range(self):
        rng = np.random.default_rng(2)
        x = rng.random((6, 4))
        labels, _ = kmeans(x, k=2, seed=7)
        self.assertEqual(len(labels), 6)
        sil = silhouette(x, labels)
        self.assertGreaterEqual(sil, -1.0)
        self.assertLessEqual(sil, 1.0)


class DDPGTest(unittest.TestCase):
    def test_act_bounded(self):
        st = DDPGSteerer(seed=7)
        for _ in range(5):
            a = st.act(np.array([0.5, 0.2, 0.3, 0.0]))
            self.assertGreaterEqual(a, 0.0)
            self.assertLessEqual(a, 1.0)

    def test_spec_reward_formula(self):
        st = DDPGSteerer(seed=7)
        # 0.5*0.1 - 0.3*(2/12) + 0.2*0.95 == 0.19
        r = st.reward(0.5, 0.6, 0.05, step=2, max_steps=12)
        self.assertAlmostEqual(r, 0.19, places=6)

    def test_online_update_runs(self):
        st = DDPGSteerer(seed=7, batch_size=4)
        s = np.array([0.5, 0.2, 0.3, 0.0])
        for _ in range(6):
            a = st.act(s)
            st.observe(s, a, 0.01, s)
        self.assertGreaterEqual(len(st.buffer), 6)


class IngestTest(unittest.TestCase):
    def test_dispatch_fixture(self):
        os.environ["COUNCIL_OFFLINE"] = "1"
        out = transcribe_dispatch_log()
        self.assertFalse(out["live_model"])
        self.assertGreater(len(out["telemetry"]), 0)
        self.assertEqual(out["telemetry"][0]["severity"], "CRITICAL")

    def test_damage_fixture(self):
        out = segment_damage()
        self.assertFalse(out["live_model"])
        self.assertEqual(len(out["zones"]), 2)
        self.assertIn("bbox", out["zones"][0])


class FenceTest(unittest.TestCase):
    def test_strips_json_fences(self):
        raw = '```json\n{"scores": {"a": [0.1, 0.2]}}\n```'
        self.assertEqual(strip_fences(raw),
                         '{"scores": {"a": [0.1, 0.2]}}')

    def test_leaves_plain_json(self):
        raw = '  {"scores": {}}  '
        self.assertEqual(strip_fences(raw), '{"scores": {}}')


class WonderTest(unittest.TestCase):
    def test_unconfigured_predicts_nothing(self):
        out = predict_paths("crisis", ["a", "b"], 0.9)
        self.assertEqual(out["paths"], [])
        self.assertFalse(out["wonder_live"])


class DevilTest(unittest.TestCase):
    def test_devil_check_offline(self):
        os.environ["COUNCIL_OFFLINE"] = "1"

        async def go():
            bus = E.EventBus()
            return await run_devil_check(SCENARIOS["reactor-failure"],
                                         seed=7, bus=bus), bus
        res, bus = asyncio.run(go())
        self.assertEqual(res.mode, "devil")
        types = [e.type for e in bus.history]
        self.assertIn(E.DEVIL_VERDICT, types)
        self.assertIn(E.RUN_FINISHED, types)
        self.assertTrue(res.dissent_log)


class CouncilTest(unittest.TestCase):
    def test_offline_replay_deterministic(self):
        os.environ["COUNCIL_OFFLINE"] = "1"

        async def go():
            bus = E.EventBus()
            r1 = await run_council(SCENARIOS["reactor-failure"], seed=7,
                                   bus=bus)
            r2 = await run_council(SCENARIOS["reactor-failure"], seed=7,
                                   bus=E.EventBus())
            return r1, r2, bus
        r1, r2, bus = asyncio.run(go())
        self.assertEqual(r1.mode, "council")
        self.assertEqual(r1.action, r2.action)
        self.assertAlmostEqual(r1.consensus, r2.consensus)
        types = [e.type for e in bus.history]
        for t in (E.RUN_STARTED, E.MODE_SELECTED, E.EVENT_START_ROUND_1,
                  E.ROUND_1_SUBMIT, E.EVENT_START_ROUND_2, E.CLUSTER_FORMED,
                  E.EVENT_START_ROUND_3, E.CONSENSUS_REACHED,
                  E.DISSENT_LOGGED, E.RUN_FINISHED, E.AUDIO_INGESTED,
                  E.DAMAGE_ZONES, E.MAP_GENERATED):
            self.assertIn(t, types)
        self.assertTrue(r1.dissent_log)
        self.assertFalse(r1.live_model)
        self.assertTrue(r1.map_artifact.endswith(".svg"))
        self.assertTrue(r1.steering)


class HealthTest(unittest.TestCase):
    def test_reports_smart_inheritance_capability(self):
        body = health()
        self.assertTrue(body["ok"])
        self.assertTrue(body["smart_inherit"])
        self.assertIn("tiers", body)


if __name__ == "__main__":
    unittest.main()
