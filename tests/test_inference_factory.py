import unittest

import numpy as np

from all_in_inference import Joint, RobotSpec
from all_in_inference.adapters import SimRobot, SinePolicy
from all_in_inference.inference import create_runtime, register_async_method
from all_in_inference.inference.contracts import InferenceMethod, MethodPolicy
from all_in_inference.scheduling import AsyncSchedule, SyncSchedule


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
        rt.run(0.08)

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
