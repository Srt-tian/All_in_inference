"""Select synchronous or asynchronous inference before selecting an async method."""

from .factory import create_runtime, register_async_method

__all__ = ["create_runtime", "register_async_method"]
