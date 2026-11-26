"""Runtime settings (env-driven; secrets never default to real values)."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIORG_")

    database_url: str = "postgresql+psycopg://aiorg:aiorg@localhost:5432/aiorg"
    session_secret: str = ""
    founder_email: str = "founder@localhost"
    founder_password_hash: str = ""
    cookie_secure: bool = True
    roles_dir: str = "roles"
    static_dir: str = "web/dist"
    session_max_age: int = 60 * 60 * 12
    worker_enabled: bool = True
    echo_seconds: float = 4.0
    gateway_mode: Literal["fake", "live"] = "fake"
    ceo_live_reply: bool = False
    model_policy_path: str = "config/model_policy.yaml"
    # durable worker (S04)
    agent_concurrency: int = 2
    min_free_ram_mb: int = 1536
    stop_grace_s: float = 30.0
    orphan_after_s: float = 60.0
    crash_retry_cap: int = 3  # the Nth crashed run dead-letters the task
    transient_retries: int = 2
    fake_delay_s: float = 0.0  # tests only; honoured only when gateway_mode is fake
    fake_ignore_term: bool = False  # tests only: the fake child ignores SIGTERM
    test_crash_point: str = ""  # tests only; honoured only when gateway_mode is fake


def get_settings() -> Settings:
    return Settings()
