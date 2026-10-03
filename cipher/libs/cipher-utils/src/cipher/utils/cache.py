"""Small in-process caches for hot lookups (e.g. per-request auth)."""

from time import monotonic


class TTLCache[K, V]:
    """A dict whose entries expire `ttl_seconds` after being set.

    Per process and unbounded in time only by the TTL -- meant for small, hot,
    eventually-consistent lookups where a short staleness window is acceptable
    and writers in the same process call `pop`/`clear` to make changes immediate.
    """

    def __init__(self, *, ttl_seconds: float):
        self.ttl_seconds = ttl_seconds
        self._entries: dict[K, tuple[float, V]] = {}

    def get(self, key: K) -> V | None:
        """The cached value, or None if missing or expired."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if monotonic() >= expires_at:
            self._entries.pop(key, None)
            return None
        return value

    def set(self, key: K, value: V) -> V:
        """Cache a value and return it."""
        self._entries[key] = (monotonic() + self.ttl_seconds, value)
        return value

    def pop(self, key: K) -> None:
        """Forget one key."""
        self._entries.pop(key, None)

    def clear(self) -> None:
        """Forget everything."""
        self._entries.clear()
