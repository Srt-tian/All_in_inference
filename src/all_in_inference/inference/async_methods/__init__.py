"""Asynchronous method plugins: Naive, Temporal Smoothing, Temporal Ensemble, Legato, and application registrations."""

from ..contracts import InferenceMethod, MethodPolicy
from .fusion import ChunkFusion
from .legato import LegatoProtocol
from .scheduling import AsyncSchedule

__all__ = ["InferenceMethod", "MethodPolicy", "LegatoProtocol", "AsyncSchedule", "ChunkFusion"]
