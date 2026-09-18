import unittest

import numpy as np

from all_in_inference import Joint, RobotSpec
from all_in_inference.adapters import SimRobot, SinePolicy
from all_in_inference.inference import create_runtime, register_async_method
from all_in_inference.inference.async_methods import ChunkFusion
from all_in_inference.inference.contracts import InferenceMethod, MethodPolicy
from all_in_inference.scheduling import AsyncSchedule, SyncSchedule
from all_in_inference.types import ActionChunk


class FactoryTests(unittest.TestCase):
    def setUp(self):
        spec = RobotSpec("test", (Joint("j", -1, 1, 0.5),))
        self.robot = SimRobot(spec, [0])
        self.policy = SinePolicy(spec, [0])

    def test_sync_and_basic_async(self):
        for mode, schedule in [("sync", SyncSchedule), ("async", AsyncSchedule)]:
            rt = create_runtime(self.robot, policy=self.policy, inference={"mode": mode})
            self.assertIsInstance(rt.schedule, schedule)
            self.assertIs(rt.policy, self.policy)

    def test_sync_rejects_async_settings(self):
        with self.assertRaises(ValueError):
            create_runtime(
                self.robot,
                policy=self.policy,
                inference={"mode": "sync", "async": {"method": "legato"}},
            )

    def test_legato_composition(self):
        rt = create_runtime(
            self.robot,
            transport=lambda _: {"actions": np.zeros((32, 1)), "actions_model": np.zeros((50, 3))},
            inference={"mode": "async", "async": {"method": "legato"}},
        )
        self.assertIsInstance(rt.policy, MethodPolicy)
        self.assertEqual(rt.timeline.fusion.kind, "replace")
        rt.run(0.08)

    def test_local_methods_select_actual_overlap_behavior(self):
        for name, expected in [
            ("naive", [0.8, 0.8, 0.8]),
            ("temporal_smoothing", [0.2, 0.5, 0.8]),
            ("temporal_ensemble", [0.65, 0.65, 0.65]),
        ]:
            options = {"new_weight": 0.75} if name == "temporal_ensemble" else {}
            rt = create_runtime(
                self.robot,
                policy=self.policy,
                inference={"mode": "async", "async": {"method": name, "options": options}},
            )
            timeline = rt.timeline
            timeline.reset([0])
            for rid, value in enumerate([0.2, 0.8]):
                timeline.integrate(
                    ActionChunk(np.full((3, 1), value), 1, rid, timeline.generation), 0
                )
            np.testing.assert_allclose(timeline.pending(0).ravel(), expected)
            self.assertEqual(rt.summary()["inference"]["method"], name)

    def test_sync_does_not_apply_temporal_fusion(self):
        rt = create_runtime(self.robot, policy=self.policy, inference={"mode": "sync"})
        self.assertEqual(rt.timeline.fusion.kind, "replace")

    def test_invalid_fusion_options_rejected(self):
        for name, options in [
            ("naive", {"new_weight": 0.5}),
            ("temporal_ensemble", {"new_weight": float("nan")}),
            ("temporal_smoothing", {"new_weight": 0.5}),
        ]:
            with self.assertRaises(ValueError):
                create_runtime(
                    self.robot,
                    policy=self.policy,
                    inference={"mode": "async", "async": {"method": name, "options": options}},
                )

    def test_basic_alias_warns_and_is_naive(self):
        with self.assertWarns(FutureWarning):
            rt = create_runtime(
                self.robot,
                policy=self.policy,
                inference={"mode": "async", "async": {"method": "basic"}},
            )
        self.assertEqual(rt.timeline.fusion.kind, "replace")

    def test_builtin_method_names_cannot_be_overwritten(self):
        for name in ("naive", "temporal_smoothing", "temporal_ensemble", "legato"):
            with self.assertRaises(ValueError):
                register_async_method(name, InferenceMethod)

    def test_custom_method_fusion_is_explicit(self):
        register_async_method(
            "custom_temporal_test", InferenceMethod, fusion=ChunkFusion("temporal")
        )
        rt = create_runtime(
            self.robot,
            transport=lambda _: np.zeros((3, 1)),
            inference={"mode": "async", "async": {"method": "custom_temporal_test"}},
        )
        self.assertEqual(rt.timeline.fusion.kind, "temporal")

    def test_default_async_is_temporal_smoothing(self):
        rt = create_runtime(self.robot, policy=self.policy)
        self.assertEqual(rt.inference_label["method"], "temporal_smoothing")
        self.assertEqual(rt.timeline.fusion.kind, "temporal")

    def test_custom_plugin_registration(self):
        register_async_method("test_custom_factory", InferenceMethod)
        rt = create_runtime(
            self.robot,
            transport=lambda req: np.zeros((32, 1)),
            inference={"mode": "async", "async": {"method": "test_custom_factory"}},
        )
        rt.run(0.08)
        with self.assertRaises(ValueError):
            register_async_method("test_custom_factory", InferenceMethod)

    def test_unknown_method_never_falls_back(self):
        with self.assertRaises(ValueError):
            create_runtime(
                self.robot,
                transport=lambda _: None,
                inference={"mode": "async", "async": {"method": "rtc"}},
            )
