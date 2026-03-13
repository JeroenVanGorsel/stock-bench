"""Canonical runtime data models for the MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from math import sqrt
from typing import Any
from uuid import uuid4

from .config import DEFAULT_RUBRIC


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass(slots=True)
class TaskRubric:
    accuracy: float = DEFAULT_RUBRIC["accuracy"]
    usefulness: float = DEFAULT_RUBRIC["usefulness"]
    clarity: float = DEFAULT_RUBRIC["clarity"]

    def validate(self) -> None:
        total = self.accuracy + self.usefulness + self.clarity
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"rubric weights must sum to 1.0, got {total}")


@dataclass(slots=True)
class Task:
    task_id: str
    prompt: str
    domain_tags: list[str]
    primary_domain: str
    difficulty: float
    importance: float
    rubric: TaskRubric = field(default_factory=TaskRubric)
    is_ground_truth: bool = False
    ground_truth_answer: str | None = None
    generator_model_id: str = "CURATED"
    source: str = "seed"
    created_at: datetime = field(default_factory=utc_now)
    status: str = "QUEUED"
    prompt_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        item = dict(data)
        item["created_at"] = datetime.fromisoformat(item["created_at"])
        item["rubric"] = TaskRubric(**item["rubric"])
        return cls(**item)


@dataclass(slots=True)
class Bid:
    bid_id: str
    task_id: str
    model_id: str
    confidence: float
    domain_tags: list[str]
    rationale: str
    parse_status: str
    bid_received_at: datetime = field(default_factory=utc_now)
    timeout: bool = False
    thompson_sample: float | None = None
    calibration_weight: float = 1.0
    domain_boost: float = 1.0
    allocation_score: float | None = None
    was_selected: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["bid_received_at"] = self.bid_received_at.isoformat()
        return data


@dataclass(slots=True)
class EvaluationScore:
    evaluator_model_id: str
    clarity_score: float
    usefulness_score: float
    accuracy_score: float
    clarity_reasoning: str
    usefulness_reasoning: str
    accuracy_reasoning: str
    composite_score: float
    evaluator_reputation_snapshot: float
    parse_status: str = "CLEAN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ModelState:
    model_id: str
    display_name: str
    provider: str
    api_model: str
    alpha: float = 1.0
    beta: float = 1.0
    calibration_score: float = 1.0
    calibration_error_ema: float = 0.0
    evaluator_reputation: float = 1.0
    domain_quality_scores: dict[str, float] = field(default_factory=dict)
    domain_task_counts: dict[str, int] = field(default_factory=dict)
    tasks_executed: int = 0
    tasks_evaluated: int = 0
    tasks_generated: int = 0
    refusal_count: int = 0
    timeout_count: int = 0
    null_bid_count: int = 0
    ipo_rounds_completed: int = 0
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def stock_price(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def volatility(self) -> float:
        n = self.alpha + self.beta
        return sqrt((self.alpha * self.beta) / (n * n * (n + 1)))

    def mean_quality_for_domain(self, domain: str) -> float:
        return self.domain_quality_scores.get(domain, self.stock_price)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        data["stock_price"] = self.stock_price
        data["volatility"] = self.volatility
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelState":
        item = dict(data)
        item.pop("stock_price", None)
        item.pop("volatility", None)
        item["created_at"] = datetime.fromisoformat(item["created_at"])
        item["updated_at"] = datetime.fromisoformat(item["updated_at"])
        return cls(**item)


@dataclass(slots=True)
class RoundResult:
    round_id: str
    cycle_number: int
    task: dict[str, Any]
    executor_model_id: str
    bid: dict[str, Any]
    execution_response: str
    execution_outcome: str
    quality_score: float
    quality_score_std: float
    evaluator_count: int
    brier_score: float
    is_ground_truth_round: bool
    objective_score: float | None
    evaluations: list[dict[str, Any]]
    created_at: datetime = field(default_factory=utc_now)
    provisional: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data
