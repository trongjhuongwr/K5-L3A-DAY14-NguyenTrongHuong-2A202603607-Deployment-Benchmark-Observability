"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.
"""
import os
from dataclasses import dataclass, field


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name, "").strip()
    return int(val) if val else default


def _get_float(name: str, default: float) -> float:
    val = os.getenv(name, "").strip()
    return float(val) if val else default


@dataclass
class Settings:
    port: int = field(default_factory=lambda: _get_int("PORT", 8000))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))
    rate_limit_per_minute: int = field(default_factory=lambda: _get_int("RATE_LIMIT_PER_MINUTE", 10))
    daily_budget_usd: float = field(default_factory=lambda: _get_float("DAILY_BUDGET_USD", 1.0))
    monthly_budget_usd: float = field(default_factory=lambda: _get_float("MONTHLY_BUDGET_USD", 10.0))


settings = Settings()
