import threading
import time
import unittest
from dataclasses import replace

import numpy as np

from all_in_inference import Joint, RobotSpec, Runtime, RuntimeConfig, RuntimeFault
from all_in_inference.adapters import CallablePolicy, SimRobot, SinePolicy
from all_in_inference.scheduling import AsyncSchedule, SyncSchedule
from all_in_inference.types import Observation


class RecordingRobot(SimRobot):
    def __init__(self, spec, initial):
        super().__init__(spec, initial)
        self.calls = []

    def write(self, position):
        self.calls.append((threading.get_ident(), time.monotonic(), position.copy()))
        super().write(position)


class RuntimeTests(unittest.TestCase):
    def make(self, n=7, config=None, schedule=None, policy=None):
        spec = RobotSpec(f"robot-{n}", tuple(Joint(f"j{i}", -2, 2, 1) for i in range(n)))
        robot = RecordingRobot(spec, np.zeros(n))
        runtime = Runtime(
            robot,
            policy or SinePolicy(spec, np.zeros(n), horizon=8, latency=0.01),
            config,
            schedule,
        )
        return robot, runtime

    def test_arbitrary_dimensions_single_writer_and_hold(self):
        for dim in (1, 7, 8, 14, 19):
            with self.subTest(dim=dim):
                robot, runtime = self.make(dim)
                summary = runtime.run(0.1)
                self.assertGreater(summary["commands"], 5)
                self.assertEqual(robot.hold_count, 1)
                self.assertEqual({row[0] for row in robot.calls}, {threading.get_ident()})
                self.assertEqual(len(runtime.timeline.pending(0)), 0)

    def test_sync_and_async_time_semantics(self):
        for schedule in (SyncSchedule(), AsyncSchedule(20)):
            robot, runtime = self.make(schedule=schedule)
            runtime.run(0.45)
            events = runtime.summary()["inference_events"]
            self.assertGreaterEqual(len(events), 2)
            for event in events:
                if isinstance(schedule, SyncSchedule):
                    self.assertGreater(event["output_start_tick"], event["arrival_tick"])
                else:
                    self.assertEqual(event["output_start_tick"], event["requested_tick"])

    def test_delayed_policy_does_not_block_writer(self):
        def slow(req):
            time.sleep(0.09)
            return np.zeros((15, len(req.observation.position)))

        _, runtime = self.make(policy=CallablePolicy(slow))
        summary = runtime.run(0.24)
        self.assertGreater(summary["commands"], 20)
        self.assertGreater(summary["inference_events"][0]["dropped"], 0)

    def test_policy_timeout_and_no_late_writes(self):
        def slow(req):
            time.sleep(0.12)
            return np.ones((8, 7))

        robot, runtime = self.make(
            policy=CallablePolicy(slow), config=RuntimeConfig(policy_timeout=0.03)
        )
        with self.assertRaisesRegex(RuntimeFault, "deadline"):
            runtime.run(0.5)
        writes = len(robot.calls)
        time.sleep(0.02)
        self.assertEqual(writes, len(robot.calls))
        self.assertEqual(robot.hold_count, 1)
        np.testing.assert_equal(robot.read().position, np.zeros(7))

    def test_inference_exception_propagates(self):
        def broken(req):
            raise ValueError("decode failed")

        robot, runtime = self.make(policy=CallablePolicy(broken))
        with self.assertRaisesRegex(RuntimeFault, "decode failed"):
            runtime.run(0.1)
        self.assertEqual(robot.hold_count, 1)

    def test_stop_is_idempotent_and_no_post_return_commands(self):
        robot, runtime = self.make()
        timer = threading.Timer(0.08, runtime.stop)
        timer.start()
        try:
            runtime.run(0.5)
        finally:
            timer.join()
        count = len(robot.calls)
        runtime.stop()
        time.sleep(0.02)
        self.assertEqual(len(robot.calls), count)
        self.assertEqual(robot.hold_count, 1)

    def test_stale_state_rejected_before_start(self):
        robot, runtime = self.make()
        robot.read = lambda: Observation(np.zeros(7), time.monotonic() - 10)
        with self.assertRaisesRegex(RuntimeFault, "stale"):
            runtime.run(0.1)
        self.assertEqual(robot.calls, [])

    def test_stale_feedback_during_execution_never_used_for_hold(self):
        robot, runtime = self.make()
        original_read = robot.read
        reads = 0

        def becomes_stale():
            nonlocal reads
            reads += 1
            obs = original_read()
            return obs if reads < 3 else Observation(obs.position, time.monotonic() - 10)

        robot.read = becomes_stale
        with self.assertRaisesRegex(RuntimeFault, "stale"):
            runtime.run(0.3)
        self.assertEqual(robot.hold_count, 0)
        self.assertTrue(
            any("Final measured hold unavailable" in f for f in runtime.summary()["faults"])
        )

    def test_expired_chunks_eventually_fault_on_underrun(self):
        def expired(req):
            time.sleep(0.06)
            return np.zeros((1, 7))

        robot, runtime = self.make(
            policy=CallablePolicy(expired), config=RuntimeConfig(underrun_timeout=0.1)
        )
        with self.assertRaisesRegex(RuntimeFault, "horizon exhausted"):
            runtime.run(0.4)
        self.assertEqual(runtime.summary()["inference_events"][0]["reason"], "expired")
        self.assertEqual(robot.hold_count, 1)

    def test_worker_join_timeout_cannot_resurrect_commands(self):
        def late(req):
            time.sleep(0.15)
            return np.ones((8, 7))

        robot, runtime = self.make(
            policy=CallablePolicy(late),
            config=RuntimeConfig(policy_timeout=0.025, worker_join_timeout=0.005),
        )
        with self.assertRaisesRegex(RuntimeFault, "Worker did not exit"):
            runtime.run(0.4)
        count = len(robot.calls)
        time.sleep(0.18)
        self.assertEqual(len(robot.calls), count)
        np.testing.assert_equal(robot.read().position, np.zeros(7))

    def test_command_slowdown_skips_slots(self):
        robot, runtime = self.make()
        original = robot.write

        def slow_write(q):
            time.sleep(0.012)
            original(q)

        robot.write = slow_write
        result = runtime.run(0.1)
        self.assertGreater(result["skipped_control_slots"], 0)
        self.assertLess(result["commands"], 12)

    def test_bounded_recording(self):
        _, runtime = self.make(config=RuntimeConfig(trace_capacity=3))
        result = runtime.run(0.1)
        self.assertEqual(result["retained_samples"], 3)
        self.assertGreater(result["dropped_trace_samples"], 0)

    def test_rate_and_shape_config_rejected(self):
        for kwargs in (
            {"control_hz": 0},
            {"action_hz": 300},
            {"policy_timeout": float("nan")},
            {"trace_capacity": 0},
            {"interpolation": "bad"},
        ):
            with self.assertRaises(ValueError):
                replace(RuntimeConfig(), **kwargs)


if __name__ == "__main__":
    unittest.main()
