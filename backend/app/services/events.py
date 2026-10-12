"""Tiny in-process event bus feeding the Server-Sent Events stream.

Routes run in a thread pool, so publishing is thread-safe and the SSE endpoint
simply reads every event newer than the last sequence number it has seen.
"""
import threading
from collections import deque
from typing import Any

_lock = threading.Lock()
_events: deque[tuple[int, str, dict[str, Any]]] = deque(maxlen=500)
_seq = 0


def publish(kind: str, data: dict[str, Any] | None = None) -> None:
    global _seq
    with _lock:
        _seq += 1
        _events.append((_seq, kind, data or {}))


def since(last_seq: int) -> list[tuple[int, str, dict[str, Any]]]:
    with _lock:
        return [e for e in _events if e[0] > last_seq]


def current_seq() -> int:
    with _lock:
        return _seq
