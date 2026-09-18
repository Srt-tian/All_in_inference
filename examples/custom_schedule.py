"""A bounded-horizon refill schedule. Import and pass to Runtime(schedule=...)."""

from all_in_inference.scheduling import AsyncSchedule


class LowWatermarkSchedule(AsyncSchedule):
    """Infer only when remaining future ticks fall below the watermark.

    It retains async request-time alignment; this is not model-specific RTC.
    """

    def __init__(self, watermark_steps=12, inference_hz=10):
        super().__init__(inference_hz)
        if type(watermark_steps) is not int or watermark_steps < 1:
            raise ValueError("watermark_steps must be a positive integer")
        self.watermark = watermark_steps

    def ready(self, tick, end_tick, since_request):
        return end_tick - tick <= self.watermark and super().ready(tick, end_tick, since_request)
