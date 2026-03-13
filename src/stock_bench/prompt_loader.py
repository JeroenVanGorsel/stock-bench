"""Helpers for prompt template loading."""

from __future__ import annotations

from functools import lru_cache

from .config import PROMPTS_DIR


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")
