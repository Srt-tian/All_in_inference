"""Reusable overlap fusion selected by the asynchronous method, not the controller."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkFusion:
    kind: str = "replace"
    new_weight: float = 0.6

    def __post_init__(self):
        if self.kind not in {"replace", "temporal", "ensemble"}:
            raise ValueError("Unknown chunk fusion")
        if not math.isfinite(self.new_weight) or not 0 < self.new_weight <= 1:
            raise ValueError("new_weight must be finite and in (0, 1]")

    def blend(self, old, new, index, count, mask):
        result = new.copy()
        if self.kind != "replace":
            weight = (
                self.new_weight
                if self.kind == "ensemble"
                else (index / (count - 1) if count > 1 else 0.0)
            )
            result[mask] = (1 - weight) * old[mask] + weight * new[mask]
        return result
