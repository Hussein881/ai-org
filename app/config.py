"""Runtime settings (env-driven; secrets never default to real values)."""

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


def get_settings() -> Settings:
    return Settings()
