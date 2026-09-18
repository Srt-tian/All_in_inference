"""Asynchronous request scheduling."""


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
