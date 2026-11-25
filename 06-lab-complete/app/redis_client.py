"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
"""
import redis

from app.config import settings


def _create_client():
    if not settings.redis_url:
        return None
    try:
        return redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    except Exception:
        return None


r = _create_client()


def redis_healthy() -> bool:
    """Kiểm tra kết nối Redis cho /ready (lỗi kết nối → False)."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False


def close_redis() -> None:
    """Đóng kết nối Redis khi shutdown."""
    if r is not None:
        try:
            r.close()
        except Exception:
            pass
