"""Legato asynchronous client protocol scaffold."""

import math

from ..contracts import InferenceMethod, Prediction


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
