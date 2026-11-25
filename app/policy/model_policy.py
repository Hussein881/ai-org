"""Model policy loader. Validation can only narrow the hard-coded data-class floor."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from app.gateway.types import DataClass

PUBLIC_ONLY: frozenset[str] = frozenset({"gemini_api", "openrouter_free"})
KNOWN_PROVIDERS = frozenset(
    {
        "fake",
        "claude_cli",
        "codex_cli",
        "anthropic_api",
        "gemini_api",
        "openrouter_free",
        "openai_api",
    }
)


class Limit(BaseModel):
    window: Literal["5h", "day", "month"]
    max_calls: int | None = None
    max_usd: float | None = None
    model: str | None = None
    hard: bool = True

    @model_validator(mode="after")
    def _one_unit(self) -> "Limit":
        if (self.max_calls is None) == (self.max_usd is None):
            raise ValueError("a limit needs exactly one of max_calls / max_usd")
        return self


class ModelInfo(BaseModel):
    id: str
    price_in: float | None = None  # USD per million input tokens
    price_out: float | None = None


class ProviderPolicy(BaseModel):
    enabled: bool
    pricing_basis: Literal["subscription", "free", "api"]
    allowed_data_classes: list[DataClass]
    limits: list[Limit] = Field(default_factory=list)
    models: dict[str, ModelInfo]


class ModelPolicy(BaseModel):
    day_tz: str = "UTC"
    unknown_call_usd: float = 0.05
    prefer_api_above_pct: int = 70
    prefer_api_roles: list[str] = Field(default_factory=list)
    providers: dict[str, ProviderPolicy]
    routes: dict[str, list[str]]
    prompt_caps: dict[str, int] = Field(default_factory=lambda: {"default": 30000})

    @model_validator(mode="after")
    def _validate(self) -> "ModelPolicy":
        unknown = set(self.providers) - KNOWN_PROVIDERS
        if unknown:
            raise ValueError(f"unknown providers: {sorted(unknown)}")
        for name, p in self.providers.items():
            if "secret" in p.allowed_data_classes:
                raise ValueError(f"{name}: `secret` can never be sent to any provider")
            if name in PUBLIC_ONLY and p.allowed_data_classes != ["public"]:
                raise ValueError(f"{name}: free tiers accept public data only")
        for route, entries in self.routes.items():
            for entry in entries:
                prov, _, model = entry.partition(":")
                if prov not in self.providers or model not in self.providers[prov].models:
                    raise ValueError(f"route {route}: unknown provider/model {entry!r}")
        return self

    def route_for(self, role: str, purpose: str = "default") -> list[tuple[str, str]]:
        key = f"{role}.{purpose}" if f"{role}.{purpose}" in self.routes else role
        if key not in self.routes:
            raise KeyError(f"no route for role {role!r}")
        out: list[tuple[str, str]] = []
        for entry in self.routes[key]:
            prov, _, model = entry.partition(":")
            out.append((prov, model))
        return out

    def cap_for(self, role: str) -> int:
        return self.prompt_caps.get(role, self.prompt_caps.get("default", 30000))


def load_model_policy(path: str | Path) -> ModelPolicy:
    return ModelPolicy.model_validate(yaml.safe_load(Path(path).read_text()))


@lru_cache
def cached_policy(path: str) -> ModelPolicy:
    return load_model_policy(path)
