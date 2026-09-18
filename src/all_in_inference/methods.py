"""Model-method lifecycle, independent of scheduling and hardware control.

LegatoProtocol is a client protocol scaffold, not a Legato algorithm implementation.
"""

import math
from dataclasses import dataclass

import numpy as np

from .types import Request, frozen_array


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


class LegatoProtocol(InferenceMethod):
    """Legato-style payload fields with separate model-space history.

    Confirm field names and action-time semantics with your deployed server.
    decode_actions can perform robot-space decoding without altering actions_model.
    """

    def __init__(
        self,
        chunk_size=50,
        ramp_down=22,
        expected_model_shape=None,
        encode_observation=None,
        decode_actions=None,
    ):
        if type(chunk_size) is not int or chunk_size < 1:
            raise ValueError("chunk_size must be a positive integer")
        if type(ramp_down) is not int or not 0 <= ramp_down <= chunk_size:
            raise ValueError("ramp_down must be between zero and chunk_size")
        self.chunk_size, self.ramp_down = chunk_size, ramp_down
        self.expected_model_shape = expected_model_shape
        self.encode_observation = encode_observation or (
            lambda req: {"state": req.observation.position.copy()}
        )
        self.decode_actions = decode_actions or (lambda out, req: out["actions"])
        self.last_latency_s = 0.0

    def reset(self, generation):
        self.last_latency_s = 0.0

    def build_payload(self, request, history):
        if request.request_tick is None:
            raise ValueError("LegatoProtocol requires request_tick")
        delay = min(self.chunk_size, math.ceil(self.last_latency_s * request.action_hz))
        consumed = 0
        payload = dict(self.encode_observation(request))
        if history is not None:
            consumed = max(
                0, math.floor(request.request_tick) - history.integration.output_start_tick + 1
            )
            model = history.prediction.actions_model
            if model is not None:
                payload["prev_action_chunk_model"] = model.copy()
        payload.update(
            inference_delay=delay,
            execute_horizon=min(self.chunk_size, consumed + delay),
            ramp_down=self.ramp_down,
        )
        return payload

    def decode(self, output, request):
        prediction = Prediction(self.decode_actions(output, request), output.get("actions_model"))
        if self.expected_model_shape is not None:
            if prediction.actions_model is None or (
                prediction.actions_model.shape != tuple(self.expected_model_shape)
            ):
                raise ValueError("Server actions_model does not match configured model shape")
        return prediction

    def on_integrated(self, request, prediction, feedback):
        self.last_latency_s = feedback.latency_s
