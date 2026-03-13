"""OpenAI client."""

from __future__ import annotations

import httpx

from ..config import get_settings
from .base import ProviderClient, ProviderError, ProviderResponse


class OpenAIClient(ProviderClient):
    url = "https://api.openai.com/v1/chat/completions"

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
        if not settings.openai_api_key:
            raise ProviderError("OPENAI_API_KEY is not configured")
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(self.url, headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]
        return ProviderResponse(
            content=message.get("content", ""),
            raw=data,
            usage=data.get("usage"),
        )
