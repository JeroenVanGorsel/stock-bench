"""Scoring and market-state helpers."""

from __future__ import annotations

import random
import statistics

from .models import EvaluationScore, ModelState, Task


def brier_score(confidence: float, quality_score: float) -> float:
    return max(0.0, min(1.0, (confidence - quality_score) ** 2))


def weighted_quality_score(evaluations: list[EvaluationScore]) -> tuple[float, float]:
    if not evaluations:
        return 0.0, 0.0
    total_weight = sum(max(0.1, item.evaluator_reputation_snapshot) for item in evaluations)
    weighted_sum = sum(
        item.composite_score * max(0.1, item.evaluator_reputation_snapshot)
        for item in evaluations
    )
    mean = weighted_sum / total_weight
    std = statistics.pstdev([item.composite_score for item in evaluations]) if len(evaluations) > 1 else 0.0
    return mean, std


def objective_anchor_score(task: Task, response_text: str) -> float | None:
    if not task.is_ground_truth or not task.ground_truth_answer:
        return None
    expected = task.ground_truth_answer.strip().lower()
    actual = response_text.strip().lower()
    if expected == actual:
        return 1.0
    if expected in actual:
        return 0.8
    return 0.0


def update_executor_state(model: ModelState, task: Task, quality_score: float, confidence: float) -> float:
    model.alpha += quality_score
    model.beta += 1.0 - quality_score
    score = brier_score(confidence, quality_score)
    model.calibration_error_ema = 0.8 * model.calibration_error_ema + 0.2 * score
    model.calibration_score = max(0.0, min(1.0, 1.0 - model.calibration_error_ema))
    model.tasks_executed += 1
    model.ipo_rounds_completed += 1
    count = model.domain_task_counts.get(task.primary_domain, 0)
    mean = model.domain_quality_scores.get(task.primary_domain, model.stock_price)
    new_count = count + 1
    model.domain_task_counts[task.primary_domain] = new_count
    model.domain_quality_scores[task.primary_domain] = ((mean * count) + quality_score) / new_count
    return score


def update_evaluator_reputation(model: ModelState, evaluator_score: float, objective_score: float | None) -> None:
    model.tasks_evaluated += 1
    if objective_score is None:
        return
    agreement = max(0.0, 1.0 - abs(evaluator_score - objective_score))
    model.evaluator_reputation = 0.85 * model.evaluator_reputation + 0.15 * agreement


def sample_allocation_score(model: ModelState, confidence: float, bootstrap: bool) -> tuple[float, float]:
    sample = random.betavariate(model.alpha, model.beta)
    if bootstrap:
        return sample, random.random()
    score = sample * max(0.25, model.calibration_score) * (0.5 + 0.5 * confidence)
    return sample, score
