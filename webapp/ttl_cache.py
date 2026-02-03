import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class _TTLItem:
    value: Any
    expires_at: float


class TTLCache:
    def __init__(self, ttl_seconds: int, maxsize: int = 512) -> None:
        self.ttl_seconds = ttl_seconds
        self.maxsize = maxsize
        self._lock = threading.RLock()
        self._store: Dict[str, _TTLItem] = {}
        self._lru: List[str] = []

    def _prune(self) -> None:
        now = time.time()
        # remove expired
        expired = [k for k, v in self._store.items() if v.expires_at <= now]
        for k in expired:
            self._store.pop(k, None)
            try:
                self._lru.remove(k)
            except ValueError:
                pass

        # enforce size
        while len(self._lru) > self.maxsize:
            oldest = self._lru.pop(0)
            self._store.pop(oldest, None)

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            self._prune()
            item = self._store.get(key)
            if not item:
                return None
            # LRU bump
            try:
                self._lru.remove(key)
            except ValueError:
                pass
            self._lru.append(key)
            return item.value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._prune()
            if key in self._store:
                self._store[key] = _TTLItem(value=value, expires_at=time.time() + self.ttl_seconds)
                try:
                    self._lru.remove(key)
                except ValueError:
                    pass
                self._lru.append(key)
                return

            self._store[key] = _TTLItem(value=value, expires_at=time.time() + self.ttl_seconds)
            self._lru.append(key)
            self._prune()