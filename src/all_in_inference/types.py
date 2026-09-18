"""Canonical robot-space positions: radians for revolute, metres for prismatic axes."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np


def frozen_array(value) -> np.ndarray:
    out = np.array(value, dtype=float, copy=True)
    out.setflags(write=False)
    return out


@dataclass(frozen=True)
class Joint:
    name: str
    lower: float
    upper: float
    max_velocity: float
    kind: str = "revolute"
    blend: bool = True
    group: str = "arm"

    def __post_init__(self):
        if not self.name or self.kind not in {"revolute", "prismatic", "discrete"}:
            raise ValueError("Joint requires a name and a supported kind")
        if not all(math.isfinite(x) for x in (self.lower, self.upper, self.max_velocity)):
            raise ValueError("Joint bounds and velocity must be finite")
        if self.lower >= self.upper or self.max_velocity <= 0:
            raise ValueError("Invalid joint bounds / velocity")
        if self.kind == "discrete" and self.blend:
            raise ValueError("Discrete joints must set blend=false")


@dataclass(frozen=True)
class RobotSpec:
    name: str
    joints: tuple[Joint, ...]

    def __post_init__(self):
        object.__setattr__(self, "joints", tuple(self.joints))
        if not self.joints or len({j.name for j in self.joints}) != len(self.joints):
            raise ValueError("Joint names must be unique and nonempty")

    @property
    def size(self):
        return len(self.joints)

    @property
    def blend_mask(self):
        return np.array([j.blend and j.kind != "discrete" for j in self.joints])

    @property
    def continuous_mask(self):
        return np.array([j.kind != "discrete" for j in self.joints])

    def validate(self, values) -> np.ndarray:
        arr = np.asarray(values, dtype=float)
        if arr.ndim not in (1, 2) or arr.shape[-1] != self.size or not np.isfinite(arr).all():
            raise ValueError(f"Expected finite (..., {self.size}) robot-space positions")
        if np.any(arr < [j.lower for j in self.joints]) or np.any(
            arr > [j.upper for j in self.joints]
        ):
            raise ValueError("Position is outside RobotSpec limits")
        return arr


@dataclass(frozen=True)
class Observation:
    position: np.ndarray
    timestamp: float  # time.monotonic(), sampled by adapter at measurement time
    sensors: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "position", frozen_array(self.position))
        # Sensor payloads must be immutable / privately owned by the adapter.
        from types import MappingProxyType

        object.__setattr__(self, "sensors", MappingProxyType(dict(self.sensors)))


@dataclass(frozen=True)
class Request:
    observation: Observation
    request_id: int
    generation: int
    start_tick: int
    action_hz: float
    pending: np.ndarray

    def __post_init__(self):
        object.__setattr__(self, "pending", frozen_array(self.pending))


@dataclass(frozen=True)
class ActionChunk:
    positions: np.ndarray
    start_tick: int
    request_id: int
    generation: int

    def __post_init__(self):
        object.__setattr__(self, "positions", frozen_array(self.positions))
        if self.positions.ndim != 2 or len(self.positions) == 0:
            raise ValueError("A chunk must have shape (nonempty horizon, action dimension)")
        if any(type(x) is not int for x in (self.start_tick, self.request_id, self.generation)):
            raise ValueError("Chunk coordinates must be integers")


class Policy(Protocol):
    def predict(self, request: Request) -> np.ndarray:
        """Return H x D absolute robot-space positions sampled at request.action_hz.

        Honour transport timeouts. Never write to a robot from this method.
        Model-space conversion belongs in this adapter, not in the controller.
        """
        ...


class RobotAdapter(Protocol):
    spec: RobotSpec

    def read(self) -> Observation:
        """Bounded-time measurement; must be safe concurrently with write()."""
        ...

    def write(self, position: np.ndarray) -> None:
        """Bounded-time direct command. No second smoothing queue or writer thread."""
        ...

    def hold(self, measured: np.ndarray) -> None:
        """One hold command, maintaining torque and grip. Never disable motors."""
        ...
