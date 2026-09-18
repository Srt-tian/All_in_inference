import unittest

import numpy as np

from all_in_inference.control import SlewLimiter
from all_in_inference.timeline import Timeline
from all_in_inference.types import ActionChunk, Joint, Observation, RobotSpec


def spec():
    return RobotSpec(
        "mixed", (Joint("joint", -10, 10, 2), Joint("grip", 0, 1, 1, "discrete", False))
    )


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.buffer = Timeline(spec())
        self.buffer.reset([0, 0])

    def chunk(self, values, start=1, rid=0, generation=None):
        return ActionChunk(
            values, start, rid, self.buffer.generation if generation is None else generation
        )

    def test_elapsed_prefix_dropped(self):
        result = self.buffer.integrate(self.chunk([[1, 0], [2, 0], [3, 1]]), 1.7)
        self.assertEqual((result.accepted, result.dropped), (2, 1))
        np.testing.assert_equal(self.buffer.pending(0), [[2, 0], [3, 1]])

    def test_fully_elapsed_not_replayed(self):
        result = self.buffer.integrate(self.chunk([[1, 1]]), 10)
        self.assertEqual(result.reason, "expired")
        np.testing.assert_equal(self.buffer.sample(10)[0], [0, 0])

    def test_out_of_order_and_reset(self):
        self.buffer.integrate(self.chunk([[1, 1]], rid=3), 0)
        self.assertEqual(
            self.buffer.integrate(self.chunk([[2, 1]], rid=2), 0).reason, "out_of_order"
        )
        old = self.chunk([[2, 1]], rid=4)
        self.buffer.reset([0, 0])
        self.assertEqual(self.buffer.integrate(old, 0).reason, "generation")

    def test_consumed_ticks_cannot_be_rewritten(self):
        self.buffer.integrate(self.chunk([[1, 0], [2, 0], [3, 0]]), 0)
        self.buffer.sample(2.4)
        result = self.buffer.integrate(self.chunk([[9, 1], [9, 1], [9, 1]], rid=1), 0)
        self.assertEqual(result.dropped, 2)

    def test_crossfade_endpoints_and_gripper(self):
        self.buffer.integrate(self.chunk([[1, 0]] * 3), 0)
        self.buffer.integrate(self.chunk([[3, 1]] * 3, rid=1), 0)
        np.testing.assert_equal(self.buffer.pending(0), [[1, 1], [2, 1], [3, 1]])
        self.assertEqual(self.buffer.sample(0.5)[0][1], 0)
        self.assertEqual(self.buffer.sample(1)[0][1], 1)

    def test_ensemble_new_weight_explicit(self):
        self.buffer = Timeline(spec(), "ensemble", new_weight=0.75)
        self.buffer.reset([0, 0])
        self.buffer.integrate(self.chunk([[0, 0]] * 2), 0)
        self.buffer.integrate(self.chunk([[4, 1]] * 2, rid=1), 0)
        np.testing.assert_equal(self.buffer.pending(0), [[3, 1], [3, 1]])

    def test_replacement_removes_old_tail(self):
        self.buffer.integrate(self.chunk([[1, 0]] * 8), 0)
        self.buffer.integrate(self.chunk([[2, 0]] * 2, rid=1), 0)
        self.assertEqual(self.buffer.end_tick(), 2)

    def test_cubic_no_overshoot_at_extremum(self):
        self.buffer.integrate(self.chunk([[1, 0], [2, 1], [1, 0], [0, 0]]), 0)
        values = np.array([self.buffer.sample(t)[0] for t in np.linspace(0, 4, 801)])
        self.assertTrue(np.all((values[:, 0] >= 0) & (values[:, 0] <= 2)))
        self.assertEqual(set(values[:, 1]), {0, 1})

    def test_cubic_tangent_continuity(self):
        self.buffer.integrate(self.chunk([[1, 0], [1.5, 0], [3, 0], [4, 0]]), 0)
        # Monotonic queries match the controller's clock direction.
        epsilon = 1e-5
        a, b, c = [self.buffer.sample(t)[0][0] for t in [2 - epsilon, 2, 2 + epsilon]]
        self.assertAlmostEqual((b - a) / epsilon, (c - b) / epsilon, places=3)

    def test_invalid_values_and_capacity(self):
        for values in ([[float("nan"), 0]], [[11, 0]], [[1, 0, 0]]):
            with self.assertRaises(ValueError):
                self.buffer.integrate(self.chunk(values), 0)
        with self.assertRaises(ValueError):
            self.buffer.integrate(self.chunk([[0, 0]] * 513), 0)

    def test_snapshot_owns_arrays(self):
        source = np.zeros(2)
        obs = Observation(source, 0)
        source[:] = 1
        np.testing.assert_equal(obs.position, [0, 0])
        with self.assertRaises(ValueError):
            obs.position[0] = 3

    def test_slew_bound_and_discrete_event(self):
        limiter = SlewLimiter(spec(), [0, 0])
        np.testing.assert_allclose(limiter.step([5, 1], 0.005), [0.01, 1])
        self.assertEqual(limiter.limited_steps, 1)


if __name__ == "__main__":
    unittest.main()
