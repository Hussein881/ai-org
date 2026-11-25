"""Deterministic provider for CI. Responses and failures can be scripted."""

import hashlib
from collections.abc import Callable

from app.gateway.types import ProviderRequest, ProviderResponse


class FakeProvider:
    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.calls: list[ProviderRequest] = []
        self.script: list[
            ProviderResponse | Exception | Callable[[ProviderRequest], ProviderResponse]
        ] = []
        self.is_available = True

    def available(self) -> bool:
        return self.is_available

    def call(self, req: ProviderRequest) -> ProviderResponse:
        self.calls.append(req)
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, Exception):
                raise step
            if callable(step):
                return step(req)
            return step
        digest = hashlib.sha256(req.prompt.encode()).hexdigest()[:8]
        return ProviderResponse(text=f"fake:{digest}")  # tokens unknown -> None
