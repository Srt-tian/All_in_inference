"""Scheduling extension point. Both modes leave the high-frequency writer independent."""

from typing import Protocol


class Schedule(Protocol):
    def ready(self, tick: float, end_tick: int, since_request: float) -> bool: ...
    def result_start(self, requested_tick: int, arrival_tick: int) -> int: ...


class AsyncSchedule:
    """Single in-flight request; retain request-time alignment and drop elapsed prefix."""

    def __init__(self, inference_hz=5.0):
        import math

        if not math.isfinite(inference_hz) or inference_hz <= 0:
            raise ValueError("inference_hz must be positive")
        self.period = 1 / inference_hz

    def ready(self, tick, end_tick, since_request):
        return since_request >= self.period

    def result_start(self, requested_tick, arrival_tick):
        return requested_tick


class SyncSchedule:
    """Consume one horizon, then infer. Rebase returned actions to arrival time.

    Robot holds its last command while policy is busy; the 200 Hz writer never blocks
    on predict(). Useful for policies whose first action is relative to a static state.
    """

    def ready(self, tick, end_tick, since_request):
        return tick >= end_tick

    def result_start(self, requested_tick, arrival_tick):
        return arrival_tick
