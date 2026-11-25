"""
Rate limiting (tiêu chí 7) — Sliding window lưu trong Redis Sorted Set.
"""
import math
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

_WINDOW_SECONDS = 60
_LOCK = threading.Lock()
_MEMORY_WINDOWS: dict[str, deque[float]] = defaultdict(deque)

_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry = 1
    if oldest[2] then
        retry = math.max(1, math.ceil(tonumber(oldest[2]) + window - now))
    end
    return {0, retry}
end

redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, math.ceil(window))
return {1, 0}
"""


def _check_memory(key: str, limit: int, now: float) -> None:
    with _LOCK:
        dq = _MEMORY_WINDOWS[key]
        cutoff = now - _WINDOW_SECONDS
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            retry_after = max(1, math.ceil(dq[0] + _WINDOW_SECONDS - now))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        dq.append(now)


def check_rate_limit(key: str) -> None:
    """Giới hạn RATE_LIMIT_PER_MINUTE request / 60 giây theo API key, vượt → 429 + Retry-After."""
    limit = settings.rate_limit_per_minute
    now = time.time()

    if r is not None:
        try:
            redis_key = f"ratelimit:{key}"
            member = f"{now}:{uuid.uuid4().hex}"
            allowed, retry_after = r.eval(
                _SLIDING_WINDOW_LUA,
                1,
                redis_key,
                now,
                _WINDOW_SECONDS,
                limit,
                member,
            )
            if not int(allowed):
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(int(retry_after))},
                )
            return
        except HTTPException:
            raise
        except RedisError:
            pass

    _check_memory(key, limit, now)
