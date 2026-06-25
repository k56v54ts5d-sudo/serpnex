"""Redis cache layer for external API responses (§7.3, §2).

All external API responses (SERP, backlinks, crawl, GSC) are cached with
TTLs defined in the architecture. Cache hits avoid redundant API calls and
are the primary cost-control mechanism."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

# TTLs in seconds as defined in §7.3
_TTL = {
    "crawl": 48 * 3600,       # 48 hours
    "gsc": 24 * 3600,         # 24 hours
    "serp": 48 * 3600,        # 48 hours
    "backlinks_target": 72 * 3600,   # 72 hours
    "backlinks_prospect": 24 * 3600, # 24 hours (stricter for opportunity eval)
}

_PREFIX = "serpnex:cache:"


def _cache_key(namespace: str, *parts: str) -> str:
    payload = ":".join(parts)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"{_PREFIX}{namespace}:{digest}"


class APICache:
    """Thin async wrapper around Redis for caching external API responses.

    All values are JSON-serialised. A missing key or a deserialization error
    is treated as a cache miss — never raises to the caller."""

    def __init__(self, redis_url: str = "") -> None:
        self._url = redis_url or settings.redis_url
        self._client: aioredis.Redis | None = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._url, decode_responses=True)
        return self._client

    async def get(self, namespace: str, *key_parts: str) -> Any | None:
        """Return the cached value or None on miss."""
        try:
            client = await self._get_client()
            raw = await client.get(_cache_key(namespace, *key_parts))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            return None

    async def set(self, namespace: str, value: Any, *key_parts: str) -> None:
        """Store a value with the TTL for the given namespace. Silently drops
        on error — a write failure must never abort an analysis."""
        ttl = _TTL.get(namespace, 3600)
        try:
            client = await self._get_client()
            await client.setex(_cache_key(namespace, *key_parts), ttl, json.dumps(value))
        except Exception:
            pass

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# Module-level singleton — reused across requests in the same worker process
_cache: APICache | None = None


def get_cache() -> APICache:
    global _cache
    if _cache is None:
        _cache = APICache()
    return _cache
