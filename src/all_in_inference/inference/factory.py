"""Public composition root: mode first, asynchronous method second."""

from .async_methods import AsyncSchedule, LegatoProtocol
from .contracts import InferenceMethod, MethodPolicy
from .sync import SyncSchedule

_ASYNC_METHODS = {"legato": LegatoProtocol}


def register_async_method(name, factory):
    """Register an application-owned InferenceMethod factory; never load arbitrary config code."""
    if not isinstance(name, str) or not name or name == "basic" or name in _ASYNC_METHODS:
        raise ValueError("Method name must be nonempty, unique and not reserved")
    if not callable(factory):
        raise TypeError("Method factory must be callable")
    _ASYNC_METHODS[name] = factory


def create_runtime(robot, *, inference=None, policy=None, transport=None, config=None):
    """Compose a Runtime without connecting hardware or starting threads.

    Sync/basic take a Policy. Algorithm-specific async methods take a transport
    callable; their protocol method owns payload construction and result decoding.
    Direct Runtime construction remains available for low-level custom schedulers.
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
        return Runtime(robot, policy, config, SyncSchedule())
    if mode != "async":
        raise ValueError("inference.mode must be sync or async")
    options = dict(settings.get("async", {}))
    if set(options) - {"method", "inference_hz", "options"}:
        raise ValueError("Unknown asynchronous options")
    name = options.get("method", "basic")
    method_options = dict(options.get("options", {}))
    schedule = AsyncSchedule(options.get("inference_hz", 5))
    if name == "basic":
        if policy is None or transport is not None or method_options:
            raise ValueError("Basic async requires policy and no method-specific options")
        resolved = policy
    else:
        if name not in _ASYNC_METHODS:
            raise ValueError(f"Unknown asynchronous method {name!r}; register it explicitly")
        if transport is None or policy is not None:
            raise ValueError("Algorithm-specific async requires transport, not policy")
        method = _ASYNC_METHODS[name](**method_options)
        if not isinstance(method, InferenceMethod):
            raise TypeError("Method factory must return InferenceMethod")
        resolved = MethodPolicy(transport, method)
    return Runtime(robot, resolved, config, schedule)
