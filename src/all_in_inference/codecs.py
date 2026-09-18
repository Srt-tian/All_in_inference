"""Model output ordering, affine unnormalization and observation-relative actions."""

import numpy as np

from .types import RobotSpec


class JointCodec:
    def __init__(
        self,
        spec: RobotSpec,
        model_joint_names,
        scale=None,
        offset=None,
        relative_to_observation=False,
    ):
        names = list(model_joint_names)
        if len(names) != spec.size or len(set(names)) != len(names):
            raise ValueError("Model layout must contain each robot joint exactly once")
        if set(names) != {j.name for j in spec.joints}:
            raise ValueError("Model / robot joint name sets differ")
        self.spec = spec
        self.indices = [names.index(j.name) for j in spec.joints]
        self.scale = np.ones(spec.size) if scale is None else np.array(scale, dtype=float)
        self.offset = np.zeros(spec.size) if offset is None else np.array(offset, dtype=float)
        for vector in (self.scale, self.offset):
            if vector.shape != (spec.size,) or not np.isfinite(vector).all():
                raise ValueError("Affine vectors must be finite, in model joint order")
        self.relative = relative_to_observation

    def decode(self, output, request):
        values = np.asarray(output, dtype=float)
        if values.ndim != 2 or values.shape[1] != self.spec.size:
            raise ValueError("Model output must be H x D")
        values = (values * self.scale + self.offset)[:, self.indices]
        if self.relative:
            # Every row is relative to the SAME request observation, not cumulative deltas.
            values = values + request.observation.position
        return self.spec.validate(values).copy()
