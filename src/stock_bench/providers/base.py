"""Common provider interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ProviderResponse:
    content: str
    raw: dict[str, Any]
    usage: dict[str, Any] | None = None


class ProviderError(RuntimeError):
    """Raised when a provider call fails."""


class ProviderClient:
    async def chat(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        timeout: float,
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> ProviderResponse:
        raise NotImplementedError
