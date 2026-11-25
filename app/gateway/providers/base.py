from typing import Protocol

from app.gateway.types import ProviderRequest, ProviderResponse


class Provider(Protocol):
    name: str

    def available(self) -> bool: ...

    def call(self, req: ProviderRequest) -> ProviderResponse: ...
