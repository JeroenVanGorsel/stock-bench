"""Lenient JSON parsing helpers for model outputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

try:
    import json5
except ModuleNotFoundError:  # pragma: no cover - optional in minimal environments
    json5 = json

from .config import DOMAIN_TAXONOMY


@dataclass(slots=True)
class ParsedPayload:
    data: dict[str, Any] | None
    status: str


def parse_json_payload(text: str) -> ParsedPayload:
    body = text.strip()
    if not body:
        return ParsedPayload(None, "NULL")
    for parser, status in ((json.loads, "CLEAN"), (json5.loads, "LENIENT")):
        try:
            parsed = parser(body)
            if isinstance(parsed, dict):
                return ParsedPayload(parsed, status)
        except Exception:
            continue
    match = re.search(r"\{.*\}", body, re.DOTALL)
    if match:
        try:
            parsed = json5.loads(match.group(0))
            if isinstance(parsed, dict):
                return ParsedPayload(parsed, "PARTIAL")
        except Exception:
            pass
    return ParsedPayload(None, "NULL")


def clamp_score(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(1.0, number))


def normalize_domain_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return ["unknown"]
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    if not cleaned:
        return ["unknown"]
    allowed = set(DOMAIN_TAXONOMY)
    return [item if item in allowed else "unknown" for item in cleaned]
