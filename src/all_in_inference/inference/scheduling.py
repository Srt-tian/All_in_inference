"""Scheduling extension point. Both modes leave the high-frequency writer independent."""

from typing import Protocol


class Schedule(Protocol):
    def ready(self, tick: float, end_tick: int, since_request: float) -> bool: ...
    def result_start(self, requested_tick: int, arrival_tick: int) -> int: ...
