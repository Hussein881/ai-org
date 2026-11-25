from app.gateway.providers.base import Provider
from app.gateway.providers.fake import FakeProvider


def build_registry(mode: str) -> dict[str, Provider]:
    """`fake` mode (the default; api container and CI) holds only fake providers."""
    if mode == "fake":
        return {
            name: FakeProvider(name)
            for name in (
                "fake",
                "claude_cli",
                "codex_cli",
                "anthropic_api",
                "gemini_api",
                "openrouter_free",
            )
        }
    from app.gateway.providers.live import live_providers

    return dict(live_providers())
