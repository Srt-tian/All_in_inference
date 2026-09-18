"""Public composition root: mode first, asynchronous method second."""

import warnings

from .async_methods import AsyncSchedule, LegatoProtocol
from .async_methods.fusion import ChunkFusion
from .contracts import InferenceMethod, MethodPolicy
from .sync import SyncSchedule

_LOCAL_METHODS = {
    "naive": "replace",
    "temporal_smoothing": "temporal",
    "temporal_ensemble": "ensemble",
}
_ASYNC_METHODS = {"legato": (LegatoProtocol, ChunkFusion())}


def register_async_method(name, factory, *, fusion=None):
    """Register a protocol method; optional fusion is an explicit algorithm decision."""
    if (
        not isinstance(name, str)
        or not name
        or name in {*_LOCAL_METHODS, "basic"}
        or name in _ASYNC_METHODS
    ):
        raise ValueError("Method name must be nonempty, unique and not reserved")
    if not callable(factory):
        raise TypeError("Method factory must be callable")
    if fusion is not None and not isinstance(fusion, ChunkFusion):
        raise TypeError("fusion must be ChunkFusion")
    _ASYNC_METHODS[name] = (factory, fusion or ChunkFusion())


def create_runtime(robot, *, inference=None, policy=None, transport=None, config=None):
    """Select sync or an async method without starting threads or hardware.

    Local async methods take a Policy. Protocol methods take a transport callable.
    Their fusion policy is resolved here and shared execution only applies it.
    """
    from ..runtime import Runtime

    settings = dict(inference) if inference is not None else {"mode": "async"}
    if set(settings) - {"mode", "async"}:
        raise ValueError("Unknown inference options")
    mode = settings.get("mode", "async")
    if mode == "sync":
        if "async" in settings:
            raise ValueError("Synchronous mode cannot configure asynchronous methods")
        if policy is None or transport is not None:
            raise ValueError("Synchronous mode requires policy, not transport")
        runtime = Runtime(robot, policy, config, SyncSchedule(), fusion=ChunkFusion())
        runtime.inference_label = {"mode": "sync", "method": None}
        return runtime
    if mode != "async":
        raise ValueError("inference.mode must be sync or async")
    options = dict(settings.get("async", {}))
    if set(options) - {"method", "inference_hz", "options"}:
        raise ValueError("Unknown asynchronous options")
    name = options.get("method", "temporal_smoothing")
    if name == "basic":
        warnings.warn(
            "basic is deprecated; choose naive or temporal_smoothing explicitly",
            FutureWarning,
            stacklevel=2,
        )
        name = "naive"
    method_options = dict(options.get("options", {}))
    schedule = AsyncSchedule(options.get("inference_hz", 5))
    if name in _LOCAL_METHODS:
        if policy is None or transport is not None:
            raise ValueError("Local async methods require policy, not transport")
        allowed = {"new_weight"} if name == "temporal_ensemble" else set()
        if set(method_options) - allowed:
            raise ValueError(f"Invalid options for {name}")
        fusion = ChunkFusion(_LOCAL_METHODS[name], **method_options)
        resolved = policy
    else:
        if name not in _ASYNC_METHODS:
            raise ValueError(f"Unknown asynchronous method {name!r}; register it explicitly")
        if transport is None or policy is not None:
            raise ValueError("Algorithm-specific async requires transport, not policy")
        factory, fusion = _ASYNC_METHODS[name]
        method = factory(**method_options)
        if not isinstance(method, InferenceMethod):
            raise TypeError("Method factory must return InferenceMethod")
        resolved = MethodPolicy(transport, method)
    runtime = Runtime(robot, resolved, config, schedule, fusion=fusion)
    runtime.inference_label = {"mode": "async", "method": name}
    return runtime
