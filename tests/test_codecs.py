import unittest

import numpy as np

from all_in_inference.codecs import JointCodec
from all_in_inference.types import Joint, Observation, Request, RobotSpec


class CodecTests(unittest.TestCase):
    def test_reorder_units_and_relative_origin(self):
        spec = RobotSpec(
            "mixed", (Joint("angle", -3, 3, 1), Joint("slide", 0, 1, 0.1, "prismatic"))
        )
        req = Request(Observation([0.2, 0.1], 0), 0, 1, 1, 25, np.empty((0, 2)))
        codec = JointCodec(
            spec, ["slide", "angle"], [0.001, np.pi / 180], relative_to_observation=True
        )
        np.testing.assert_allclose(codec.decode([[50, 90]], req), [[0.2 + np.pi / 2, 0.15]])

    def test_missing_joint_rejected(self):
        spec = RobotSpec("arm", (Joint("angle", -3, 3, 1),))
        with self.assertRaises(ValueError):
            JointCodec(spec, ["wrong"])


if __name__ == "__main__":
    unittest.main()
