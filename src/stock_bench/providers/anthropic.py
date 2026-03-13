"""Anthropic client."""

from __future__ import annotations

import httpx

from ..config import get_settings
from .base import ProviderClient, ProviderError, ProviderResponse


class AnthropicClient(ProviderClient):
    url = "https://api.anthropic.com/v1/messages"

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
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not configured")
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(self.url, headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        text_blocks = [block.get("text", "") for block in data.get("content", [])]
        return ProviderResponse(
            content="\n".join(part for part in text_blocks if part),
            raw=data,
            usage=data.get("usage"),
        )
