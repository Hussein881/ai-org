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


def get_settings() -> Settings:
    return Settings()
