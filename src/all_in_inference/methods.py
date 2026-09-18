"""Backward-compatible imports; new code should use inference.async_methods."""

from .inference.async_methods.legato import LegatoProtocol
from .inference.contracts import (
    InferenceMethod,
    IntegrationFeedback,
    MethodHistory,
    MethodPolicy,
    Prediction,
)

__all__ = [
    "LegatoProtocol",
    "InferenceMethod",
    "IntegrationFeedback",
    "MethodHistory",
    "MethodPolicy",
    "Prediction",
]
