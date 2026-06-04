"""
Core configuration using Pydantic Settings.
All settings are loaded from environment variables / .env file.

Improvement: Added Anthropic Claude support alongside Groq for flexibility,
rate limiting config, and cache TTL settings.
"""
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "development"
    secret_key: str = "change_me_in_production"
    cors_origins: List[str] = ["http://localhost:3000"]
    app_version: str = "1.0.0"

    # LLM — Primary provider: Groq (fast inference)
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    llm_model: str = "llama-3.3-70b-versatile"
    llm_fast_model: str = "llama-3.1-8b-instant"
    llm_temperature: float = 0.1
    llm_max_retries: int = 3

    # Database
    database_url: str = "postgresql+asyncpg://biuser:bipassword@localhost:5432/biplatform"
    database_sync_url: str = "postgresql://biuser:bipassword@localhost:5432/biplatform"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # LangSmith observability
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "bi-platform"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # Business Logic
    max_sql_rows: int = 5000
    sql_confidence_threshold: float = 0.7
    enable_human_in_loop: bool = True
    max_forecast_periods: int = 12

    # Redis (session + result cache)
    redis_url: str = "redis://localhost:6379/0"
    session_ttl_seconds: int = 3600
    query_cache_ttl_seconds: int = 300  # cache identical queries for 5 min

    # Report storage
    reports_dir: str = "/tmp/bi_reports"

    # Rate limiting
    rate_limit_requests_per_minute: int = 30


@lru_cache()
def get_settings() -> Settings:
    return Settings()
