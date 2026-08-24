"""Shared runtime state for extracted routers.

server.py is a mega-module carrying the DB handle, Pydantic models, ledger
service, and dozens of helpers. As we peel route handlers into dedicated
router files under `routers/`, they still need access to that shared state
without introducing circular imports.

`server.py` registers the state on startup by calling `register_state(...)`.
Each router imports `state` and reaches through it — never re-declaring
models or the DB client. This lets us extract routes mechanically without
rewriting the object graph they depend on.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

state = SimpleNamespace()


def register_state(**kwargs: Any) -> None:
    """Idempotent register — server.py calls this once during import."""
    for k, v in kwargs.items():
        setattr(state, k, v)


def get(name: str) -> Any:
    """Convenience getter used by routers so a missing key raises early."""
    if not hasattr(state, name):
        raise RuntimeError(f"server_state.{name} is not registered yet")
    return getattr(state, name)
