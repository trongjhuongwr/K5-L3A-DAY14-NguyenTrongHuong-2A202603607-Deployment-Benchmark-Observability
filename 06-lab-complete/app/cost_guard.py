"""
Cost guard (tiêu chí 8) — Theo dõi chi phí LLM trong Redis.
"""
import threading
from datetime import datetime, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_LOCK = threading.Lock()
_MEMORY_DAILY: dict[str, float] = {}
_MEMORY_MONTHLY: dict[str, float] = {}


def _keys() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return f"cost:daily:{now:%Y-%m-%d}", f"cost:monthly:{now:%Y-%m}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    daily_key, monthly_key = _keys()
    daily_spent = 0.0
    monthly_spent = 0.0

    if r is not None:
        try:
            vals = r.mget(daily_key, monthly_key)
            daily_spent = float(vals[0] or 0.0)
            monthly_spent = float(vals[1] or 0.0)
        except RedisError:
            with _LOCK:
                daily_spent = _MEMORY_DAILY.get(daily_key, 0.0)
                monthly_spent = _MEMORY_MONTHLY.get(monthly_key, 0.0)
    else:
        with _LOCK:
            daily_spent = _MEMORY_DAILY.get(daily_key, 0.0)
            monthly_spent = _MEMORY_MONTHLY.get(monthly_key, 0.0)

    if daily_spent >= settings.daily_budget_usd or monthly_spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Budget limit exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = round(
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K,
        8,
    )
    daily_key, monthly_key = _keys()

    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incrbyfloat(daily_key, cost)
            pipe.expire(daily_key, 2 * 86400)
            pipe.incrbyfloat(monthly_key, cost)
            pipe.expire(monthly_key, 35 * 86400)
            pipe.execute()
            return cost
        except RedisError:
            pass

    with _LOCK:
        _MEMORY_DAILY[daily_key] = _MEMORY_DAILY.get(daily_key, 0.0) + cost
        _MEMORY_MONTHLY[monthly_key] = _MEMORY_MONTHLY.get(monthly_key, 0.0) + cost
    return cost
