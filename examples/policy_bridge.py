"""Runnable mock of wrapping an existing client; no network or hardware access."""

import numpy as np

from all_in_inference import Joint, RobotSpec, Runtime
from all_in_inference.adapters import CallablePolicy, SimRobot
from all_in_inference.codecs import JointCodec


class DemoClient:
    def infer(self, payload):
        return {"actions": np.tile(payload["state"], (32, 1))}


def make_policy(client, spec):
    codec = JointCodec(spec, [j.name for j in spec.joints])
    return CallablePolicy(
        predict_fn=client.infer,
        encode_fn=lambda req: {"state": req.observation.position.copy()},
        decode_fn=lambda out, req: codec.decode(out["actions"], req),
    )


if __name__ == "__main__":
    spec = RobotSpec("demo", (Joint("joint_1", -2, 2, 0.5),))
    runtime = Runtime(SimRobot(spec, [0]), make_policy(DemoClient(), spec))
    result = runtime.run(1)
    print(f"Host command frequency: {result['measured_hz']:.2f} Hz")
