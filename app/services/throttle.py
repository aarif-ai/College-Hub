"""Tiny in-memory rate limiter (resets when the app restarts).

Good enough to slow down password guessing on a single server. For several
servers, replace it with a shared store such as Redis.
"""
import time

_EVENTS: dict[str, list[float]] = {}


def _recent(key: str, window: int) -> list[float]:
    cutoff = time.time() - window
    recent = [t for t in _EVENTS.get(key, []) if t > cutoff]
    _EVENTS[key] = recent
    return recent


def is_limited(key: str, limit: int, window: int) -> bool:
    return len(_recent(key, window)) >= limit


def hit(key: str, window: int = 600) -> None:
    _recent(key, window)
    _EVENTS.setdefault(key, []).append(time.time())


def clear(key: str) -> None:
    _EVENTS.pop(key, None)


def reset_all() -> None:
    _EVENTS.clear()
