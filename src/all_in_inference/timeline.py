"""Bounded action-time buffer. Prediction time and command time are separate clocks."""

import math
import threading
from dataclasses import dataclass

import numpy as np

from .inference.async_methods.fusion import ChunkFusion
from .types import ActionChunk, RobotSpec


@dataclass(frozen=True)
class Integration:
    accepted: int = 0
    dropped: int = 0
    reason: str = "accepted"


class Timeline:
    def __init__(
        self, spec: RobotSpec, method="replace", capacity=512, new_weight=0.6, *, fusion=None
    ):
        if type(capacity) is not int or capacity < 2:
            raise ValueError("Invalid buffer capacity / ensemble weight")
        self.fusion = fusion if fusion is not None else ChunkFusion(method, new_weight)
        self.spec, self.method, self.capacity = spec, self.fusion.kind, capacity
        self.new_weight = self.fusion.new_weight
        self.lock = threading.RLock()
        self.generation = 0
        self._latest_id = -1
        self._points: dict[int, np.ndarray] = {}
        self._cursor = -1

    def reset(self, position, tick=0):
        q = self.spec.validate(position).copy()
        if q.ndim != 1:
            raise ValueError("Initial position must be one-dimensional")
        with self.lock:
            self.generation += 1
            self._points = {tick: q}
            self._cursor = tick
            self._latest_id = -1

    def integrate(self, chunk: ActionChunk, now_tick: float) -> Integration:
        q = self.spec.validate(chunk.positions)
        if len(q) > self.capacity:
            raise ValueError("Chunk exceeds bounded buffer capacity")
        with self.lock:
            if chunk.generation != self.generation:
                return Integration(reason="generation")
            if chunk.request_id <= self._latest_id:
                return Integration(reason="out_of_order")
            floor = max(math.floor(now_tick), self._cursor)
            drop = max(0, floor + 1 - chunk.start_tick)
            self._latest_id = chunk.request_id
            if drop >= len(q):
                return Integration(dropped=len(q), reason="expired")
            start = chunk.start_tick + drop
            end = chunk.start_tick + len(q) - 1
            if end - floor > self.capacity:
                raise ValueError("Chunk extends beyond bounded timeline horizon")
            incoming = {start + i: v.copy() for i, v in enumerate(q[drop:])}
            overlap = sorted(set(incoming) & set(self._points))
            for i, tick in enumerate(overlap):
                incoming[tick] = self.fusion.blend(
                    self._points[tick], incoming[tick], i, len(overlap), self.spec.blend_mask
                )
            # New horizon is authoritative; never execute an obsolete trailing tail.
            self._points = {t: p for t, p in self._points.items() if t < start}
            self._points.update(incoming)
            self._prune(floor)
            return Integration(accepted=len(incoming), dropped=drop)

    def _prune(self, floor):
        # Two past knots retain the interpolation tangent; capacity bounds future knots.
        past = sorted(t for t in self._points if t <= floor)
        for tick in past[:-2]:
            del self._points[tick]

    def pending(self, now_tick):
        with self.lock:
            values = [p for t, p in sorted(self._points.items()) if t > now_tick]
            return np.array(values).reshape(-1, self.spec.size).copy()

    def end_tick(self):
        with self.lock:
            return max(self._points, default=-1)

    def sample(self, tick: float, interpolation="cubic") -> tuple[np.ndarray, bool]:
        if interpolation not in {"linear", "cubic"}:
            raise ValueError("Unknown interpolation")
        with self.lock:
            if not self._points:
                raise ValueError("Timeline must be reset before sampling")
            self._cursor = max(self._cursor, math.floor(tick))
            self._prune(self._cursor)
            keys = sorted(self._points)
            if tick >= keys[-1]:
                return self._points[keys[-1]].copy(), tick > keys[-1]
            if tick <= keys[0]:
                return self._points[keys[0]].copy(), False
            i = int(np.searchsorted(keys, tick)) - 1
            t0, t1 = keys[i : i + 2]
            p0, p1 = self._points[t0], self._points[t1]
            h = t1 - t0
            u = (tick - t0) / h
            out = p0.copy()  # non-blend axes use left-continuous hold until knot time
            mask = self.spec.blend_mask
            if interpolation == "linear":
                value = (1 - u) * p0 + u * p1
            else:
                secant = (p1 - p0) / h
                m0, m1 = secant.copy(), secant.copy()
                if i > 0:
                    hp = t0 - keys[i - 1]
                    dp = (p0 - self._points[keys[i - 1]]) / hp
                    m0 = _monotone_slope(dp, secant, hp, h)
                if i + 2 < len(keys):
                    hn = keys[i + 2] - t1
                    dn = (self._points[keys[i + 2]] - p1) / hn
                    m1 = _monotone_slope(secant, dn, h, hn)
                value = (
                    (2 * u**3 - 3 * u**2 + 1) * p0
                    + (u**3 - 2 * u**2 + u) * h * m0
                    + (-2 * u**3 + 3 * u**2) * p1
                    + (u**3 - u**2) * h * m1
                )
            out[mask] = value[mask]
            if u >= 1:
                out[~mask] = p1[~mask]
            return out, False


def _monotone_slope(a, b, ha, hb):
    """Weighted harmonic tangent: zero at extrema, no scalar segment overshoot."""
    result = np.zeros_like(a)
    same = (a * b) > 0
    w1, w2 = 2 * hb + ha, hb + 2 * ha
    result[same] = (w1 + w2) / (w1 / a[same] + w2 / b[same])
    return result
