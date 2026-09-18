"""Built-in safe simulation and explicit bridges to existing deployments."""

import threading
import time

import numpy as np

from .types import Observation, RobotSpec


class SimRobot:
    """Ideal position plant, not a physics simulator. Does not import a hardware SDK."""

    def __init__(self, spec: RobotSpec, initial):
        self.spec = spec
        self._q = spec.validate(initial).copy()
        self._lock = threading.Lock()
        self.hold_count = 0

    def read(self):
        with self._lock:
            return Observation(self._q, time.monotonic())

    def write(self, position):
        q = self.spec.validate(position).copy()
        with self._lock:
            self._q = q

    def hold(self, measured):
        self.write(measured)
        self.hold_count += 1


class CallbackRobot:
    """Embodiment-neutral bridge. Callbacks must satisfy RobotAdapter's contract.

    read() returns Observation; send() sends directly, with no additional worker.
    No automatic connection, motor enable, homing, disconnect or torque disable.
    """

    def __init__(self, spec, read, send, hold):
        self.spec, self._read, self._send, self._hold = spec, read, send, hold

    def read(self):
        return self._read()

    def write(self, position):
        self._send(self.spec.validate(position).copy())

    def hold(self, measured):
        self._hold(self.spec.validate(measured).copy())


class CallablePolicy:
    """Bridge SDK/HTTP/WebSocket clients with injected preprocess, predict and decode.

    predict_fn must enforce its own network timeout. decode_fn returns robot-space
    absolute positions (including unnormalization, units and embodiment mapping).
    """

    def __init__(self, predict_fn, encode_fn=lambda req: req, decode_fn=lambda out, req: out):
        self.predict_fn, self.encode_fn, self.decode_fn = predict_fn, encode_fn, decode_fn

    def predict(self, request):
        return self.decode_fn(self.predict_fn(self.encode_fn(request)), request)


class SinePolicy:
    """Deterministic synthetic chunks with simulated inference latency."""

    def __init__(self, spec, initial, horizon=32, latency=0.02):
        if type(horizon) is not int or horizon <= 0 or not np.isfinite(latency) or latency < 0:
            raise ValueError("Invalid demo horizon / latency")
        self.spec, self.initial = spec, spec.validate(initial).copy()
        self.horizon, self.latency = horizon, latency

    def predict(self, request):
        time.sleep(self.latency)
        times = (request.start_tick + np.arange(self.horizon)) / request.action_hz
        out = np.tile(self.initial, (self.horizon, 1))
        for i, joint in enumerate(self.spec.joints):
            if joint.blend:
                margin = min(self.initial[i] - joint.lower, joint.upper - self.initial[i])
                amplitude = min(margin * 0.4, joint.max_velocity / 4)
                out[:, i] += amplitude * np.sin(times * 0.8 + i * 0.1)
        return out
