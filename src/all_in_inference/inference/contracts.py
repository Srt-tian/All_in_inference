"""Model-method lifecycle, independent of scheduling and hardware control.

LegatoProtocol is a client protocol scaffold, not a Legato algorithm implementation.
"""

from dataclasses import dataclass

import numpy as np

from ..types import Request, frozen_array


@dataclass(frozen=True)
class Prediction:
    positions: np.ndarray
    actions_model: np.ndarray | None = None

    def __post_init__(self):
        object.__setattr__(self, "positions", frozen_array(self.positions))
        if self.actions_model is not None:
            model = frozen_array(self.actions_model)
            if model.ndim != 2 or not all(model.shape) or not np.isfinite(model).all():
                raise ValueError("actions_model must be a finite, nonempty H_model x D_model array")
            object.__setattr__(self, "actions_model", model)


@dataclass(frozen=True)
class IntegrationFeedback:
    output_start_tick: int
    arrival_tick: float
    latency_s: float
    accepted: int
    dropped: int
    reason: str


@dataclass(frozen=True)
class MethodHistory:
    request_id: int
    generation: int
    prediction: Prediction
    integration: IntegrationFeedback


class InferenceMethod:
    """Override payload, decoding, lifecycle and integration feedback as needed.

    Hooks run on the policy worker, never on the command thread. They must not
    access hardware. Subclasses can keep model-space caches separate from pending.
    """

    def reset(self, generation: int):
        pass

    def build_payload(self, request: Request, history: MethodHistory | None):
        return request

    def decode(self, output, request: Request) -> Prediction:
        return Prediction(output)

    def on_integrated(self, request, prediction, feedback):
        pass


class MethodPolicy:
    """Compose a transport callable with an algorithm-specific method.

    Only accepted integrations replace history. Generation changes clear it.
    The transport owns its network timeout; this object owns no control thread.
    """

    def __init__(self, transport, method: InferenceMethod):
        self.transport, self.method = transport, method
        self.history: MethodHistory | None = None
        self._generation = None

    def predict(self, request):
        if request.generation != self._generation:
            self.history = None
            self._generation = request.generation
            self.method.reset(request.generation)
        payload = self.method.build_payload(request, self.history)
        return self.method.decode(self.transport(payload), request)

    def on_integrated(self, request, prediction, feedback):
        if request.generation != self._generation:
            return
        if feedback.accepted:
            self.history = MethodHistory(
                request.request_id, request.generation, prediction, feedback
            )
        self.method.on_integrated(request, prediction, feedback)
