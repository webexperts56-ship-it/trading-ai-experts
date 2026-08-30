"""Small thread-safe TTL cache used by data providers to avoid hammering APIs."""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional


class TTLCache:
    def __init__(self, ttl: float = 15.0):
        self._ttl = ttl
        self._lock = threading.RLock()
        self._store: dict[str, tuple[float, object]] = {}

    def get(self, key: str) -> Optional[object]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.time() - ts > self._ttl:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: object) -> None:
        with self._lock:
            self._store[key] = (time.time(), value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def get_or_call(self, key: str, producer: Callable[[], object]) -> object:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = producer()
        self.set(key, value)
        return value