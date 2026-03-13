"""Runtime configuration for Stock Bench."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional in minimal environments
    def load_dotenv() -> bool:
        return False

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT_DIR / "prompts"
STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGS_DIR = ROOT_DIR / "logs"
MODELS_FILE = ROOT_DIR / "models.json"
MODELS_EXAMPLE_FILE = ROOT_DIR / "models.json.example"


@dataclass(slots=True)
class ModelSpec:
    id: str
    display_name: str
    provider: str
    api_model: str
    enabled: bool = True


@dataclass(slots=True)
class Settings:
    database_path: str
    request_timeout: float
    bootstrap_rounds: int
    min_evaluators: int
    anchor_ratio: float
    openrouter_api_key: str | None
    openai_api_key: str | None
    anthropic_api_key: str | None
    model_specs: list[ModelSpec]


def _load_model_specs() -> list[ModelSpec]:
    source_path = MODELS_FILE if MODELS_FILE.exists() else MODELS_EXAMPLE_FILE
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    return [ModelSpec(**item) for item in raw if item.get("enabled", True)]


def get_settings() -> Settings:
    return Settings(
        database_path=os.getenv("STOCK_BENCH_DATABASE", "stock_bench.db"),
        request_timeout=float(os.getenv("STOCK_BENCH_REQUEST_TIMEOUT", "60")),
        bootstrap_rounds=int(os.getenv("STOCK_BENCH_BOOTSTRAP_ROUNDS", "8")),
        min_evaluators=int(os.getenv("STOCK_BENCH_MIN_EVALUATORS", "3")),
        anchor_ratio=float(os.getenv("STOCK_BENCH_ANCHOR_RATIO", "0.2")),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        model_specs=_load_model_specs(),
    )


DOMAIN_TAXONOMY: tuple[str, ...] = (
    "formal_reasoning",
    "code_and_systems",
    "factual_synthesis",
    "creative_rhetorical",
    "ethical_nuanced_judgment",
    "structured_data_analysis",
    "instruction_following",
)


DEFAULT_RUBRIC: dict[str, float] = {
    "accuracy": 0.5,
    "usefulness": 0.35,
    "clarity": 0.15,
}


def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
