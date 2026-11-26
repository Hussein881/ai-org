from collections.abc import Callable

from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db.session import engine
from app.gateway.providers.base import Provider
from app.gateway.providers.fake import FakeProvider
from app.gateway.providers.registry import build_registry
from app.gateway.router import Gateway
from app.gateway.subproc import run_cli
from app.policy.model_policy import cached_policy
from app.workers import crash


def build_gateway(halted: Callable[[], bool] = lambda: False) -> Gateway:
    s = get_settings()
    providers = build_registry(s.gateway_mode)
    if s.gateway_mode == "fake" and (s.fake_delay_s or s.test_crash_point):
        add_test_hooks(providers, s.fake_delay_s)
    return Gateway(
        sessionmaker(engine()), cached_policy(s.model_policy_path), providers, halted=halted
    )


def add_test_hooks(providers: dict[str, Provider], delay_s: float) -> None:
    """Fake mode only: calls take real time in a real child process, so tests can kill them."""

    def on_call() -> None:
        crash.point("during_call")
        if delay_s:
            run_cli(["sleep", str(delay_s)], "", delay_s + 30)

    for p in providers.values():
        if isinstance(p, FakeProvider):
            p.on_call = on_call
