from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db.session import engine
from app.gateway.providers.registry import build_registry
from app.gateway.router import Gateway
from app.policy.model_policy import cached_policy


def build_gateway() -> Gateway:
    s = get_settings()
    return Gateway(
        sessionmaker(engine()), cached_policy(s.model_policy_path), build_registry(s.gateway_mode)
    )
