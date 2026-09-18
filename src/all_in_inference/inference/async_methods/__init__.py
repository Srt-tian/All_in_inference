"""Asynchronous method plugins: basic, Legato, and application registrations."""

from ..contracts import InferenceMethod, MethodPolicy
from .legato import LegatoProtocol
from .scheduling import AsyncSchedule

__all__ = ["InferenceMethod", "MethodPolicy", "LegatoProtocol", "AsyncSchedule"]
