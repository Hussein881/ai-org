"""Shared gateway types. Data classes are ordered: public < founder_private < secret."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

DataClass = Literal["public", "founder_private", "secret"]
PartKind = Literal["constitution", "role_card", "policy", "task", "memory", "failure"]
DATA_CLASSES: tuple[DataClass, ...] = ("public", "founder_private", "secret")
Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(UTC)


def max_class(a: DataClass, b: DataClass) -> DataClass:
    return a if DATA_CLASSES.index(a) >= DATA_CLASSES.index(b) else b


def check_class(value: str) -> DataClass:
    if value not in DATA_CLASSES:
        raise ValueError(f"unknown data_class: {value!r}")
    return value


@dataclass(frozen=True)
class PromptPart:
    kind: PartKind
    text: str
    data_class: DataClass = "public"
    untrusted: bool = False


@dataclass(frozen=True)
class ProviderRequest:
    model: str
    prompt: str
    schema: dict[str, Any] | None = None
    timeout_s: float = 120.0
    max_output_tokens: int = 1024


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class Result:
    text: str
    provider: str
    model: str
    usage_id: str
    input_tokens: int | None
    output_tokens: int | None


class GatewayError(Exception):
    pass


class RateLimited(GatewayError):
    def __init__(self, reset_at: datetime | None = None) -> None:
        super().__init__("rate limited")
        self.reset_at = reset_at


class ProviderError(GatewayError):
    """Provider failed. `kind` is a short code; raw bodies are never kept."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class MalformedOutput(ProviderError):
    def __init__(self) -> None:
        super().__init__("malformed_output")


class ProviderDisabled(GatewayError):
    pass


class DataClassRefused(GatewayError):
    pass


class PromptTooLarge(GatewayError):
    pass


class AllRoutesFailed(GatewayError):
    pass


class Queued(GatewayError):
    def __init__(self, resets_at: datetime) -> None:
        super().__init__(f"queued until {resets_at.isoformat()}")
        self.resets_at = resets_at
