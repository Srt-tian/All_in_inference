import unittest

import numpy as np

from all_in_inference import Joint, RobotSpec, Runtime
from all_in_inference.adapters import SimRobot
from all_in_inference.methods import IntegrationFeedback, LegatoProtocol, MethodPolicy
from all_in_inference.types import Observation, Request


class MethodTests(unittest.TestCase):
    def request(self, generation=1, tick=0):
        return Request(
            Observation([0, 0], 0), 0, generation, 1, 25, np.empty((0, 2)), request_tick=tick
        )

    def make(self):
        return MethodPolicy(
            lambda payload: {"actions": np.zeros((8, 2)), "actions_model": np.ones((16, 5))},
            LegatoProtocol(16, 4, (16, 5)),
        )

    def test_separate_spaces_and_timed_payload(self):
        policy = self.make()
        req = self.request()
        prediction = policy.predict(req)
        self.assertEqual(prediction.positions.shape, (8, 2))
        policy.on_integrated(req, prediction, IntegrationFeedback(1, 2, 0.08, 6, 2, "accepted"))
        payload = policy.method.build_payload(self.request(tick=4), policy.history)
        self.assertEqual(payload["inference_delay"], 2)
        self.assertEqual(payload["execute_horizon"], 6)
        self.assertEqual(payload["ramp_down"], 4)
        self.assertEqual(payload["prev_action_chunk_model"].shape, (16, 5))
        payload["prev_action_chunk_model"][:] = 9
        self.assertEqual(prediction.actions_model[0, 0], 1)

    def test_expired_result_does_not_replace_history(self):
        policy = self.make()
        req = self.request()
        prediction = policy.predict(req)
        policy.on_integrated(req, prediction, IntegrationFeedback(1, 9, 0.1, 0, 8, "expired"))
        self.assertIsNone(policy.history)
        self.assertEqual(policy.method.last_latency_s, 0.1)

    def test_generation_reset_clears_history_and_latency(self):
        policy = self.make()
        req = self.request()
        prediction = policy.predict(req)
        policy.on_integrated(req, prediction, IntegrationFeedback(1, 2, 0.08, 6, 2, "accepted"))
        policy.predict(self.request(generation=2))
        self.assertIsNone(policy.history)
        self.assertEqual(policy.method.last_latency_s, 0)
        policy.on_integrated(req, prediction, IntegrationFeedback(1, 2, 0.08, 6, 2, "accepted"))
        self.assertIsNone(policy.history)

    def test_bad_model_shape_rejected(self):
        method = LegatoProtocol(expected_model_shape=(50, 7))
        with self.assertRaises(ValueError):
            method.decode(
                {"actions": np.zeros((8, 2)), "actions_model": np.zeros((8, 2))}, self.request()
            )

    def test_runtime_lifecycle_and_plain_policy_compatibility(self):
        payloads = []

        def transport(payload):
            payloads.append(payload)
            return {"actions": np.zeros((16, 2)), "actions_model": np.ones((20, 5))}

        policy = MethodPolicy(transport, LegatoProtocol(20, 4, (20, 5)))
        spec = RobotSpec("test", (Joint("a", -1, 1, 1), Joint("b", -1, 1, 1)))
        Runtime(SimRobot(spec, [0, 0]), policy).run(0.25)
        self.assertGreaterEqual(len(payloads), 2)
        self.assertNotIn("prev_action_chunk_model", payloads[0])
        self.assertIn("prev_action_chunk_model", payloads[1])
