"""Last command-space guard, independent of the robot's number of arms / joints."""

import numpy as np

from .types import RobotSpec


class SlewLimiter:
    def __init__(self, spec: RobotSpec, initial):
        self.spec = spec
        self.position = spec.validate(initial).copy()
        self.limited_steps = 0

    def step(self, target, dt):
        if not np.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be positive")
        target = self.spec.validate(target)
        if target.ndim != 1:
            raise ValueError("Target must be a vector")
        cap = np.array([j.max_velocity for j in self.spec.joints]) * dt
        delta = target - self.position
        mask = self.spec.continuous_mask
        clipped = np.clip(delta, -cap, cap)
        if np.any(np.abs(delta[mask]) > cap[mask] + 1e-12):
            self.limited_steps += 1
        delta[mask] = clipped[mask]
        self.position = self.position + delta
        return self.position.copy()
