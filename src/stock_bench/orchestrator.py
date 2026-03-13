"""Sequential round loop orchestration."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime
from typing import Any

from .config import get_settings
from .market import objective_anchor_score, sample_allocation_score, update_evaluator_reputation, update_executor_state, weighted_quality_score
from .models import Bid, EvaluationScore, ModelState, RoundResult, Task, new_id
from .parsing import clamp_score, normalize_domain_tags, parse_json_payload
from .prompt_loader import load_prompt
from .providers.anthropic import AnthropicClient
from .providers.base import ProviderClient, ProviderError
from .providers.openai import OpenAIClient
from .providers.openrouter import OpenRouterClient
from .storage import SQLiteRepository
from .tasks import generate_task, seed_tasks


logger = logging.getLogger(__name__)


class MarketOrchestrator:
    def __init__(self, repository: SQLiteRepository):
        self.repository = repository
        self.settings = get_settings()

    def bootstrap(self) -> None:
        existing_models = {state.model_id for state in self.repository.list_model_states()}
        for spec in self.settings.model_specs:
            if spec.id not in existing_models:
                logger.info("registering model %s via %s", spec.id, spec.provider)
                self.repository.upsert_model_state(
                    ModelState(
                        model_id=spec.id,
                        display_name=spec.display_name,
                        provider=spec.provider,
                        api_model=spec.api_model,
                    )
                )
        if not self.repository.list_tasks(limit=1):
            logger.info("seeding initial task bank")
            for task in seed_tasks():
                self.repository.queue_task(task)

    def _provider_for(self, model: ModelState) -> ProviderClient:
        if model.provider == "openrouter":
            return OpenRouterClient()
        if model.provider == "openai":
            return OpenAIClient()
        if model.provider == "anthropic":
            return AnthropicClient()
        raise ProviderError(f"Unsupported provider: {model.provider}")

    def _ensure_task_supply(self, active_models: list[ModelState]) -> None:
        queued = [task for task in self.repository.list_tasks(limit=20) if task.status == "QUEUED"]
        if queued:
            return
        logger.info("task queue empty; adding fallback seed tasks")
        for task in seed_tasks()[:2]:
            if not self.repository.task_exists_by_hash(task.prompt_hash):
                self.repository.queue_task(task)

    async def _maybe_generate_task(self, models: list[ModelState]) -> None:
        active = [model for model in models if model.active]
        if not active:
            return
        queued = [task for task in self.repository.list_tasks(limit=20) if task.status == "QUEUED"]
        if len(queued) >= 5:
            return
        generator = min(active, key=lambda item: item.tasks_generated)
        logger.info("attempting generated task via %s", generator.model_id)
        try:
            task = await generate_task(
                self._provider_for(generator),
                generator.api_model,
                generator.model_id,
                self.settings.request_timeout,
            )
        except Exception as exc:
            logger.warning("generated task failed for %s: %s", generator.model_id, exc)
            return
        if task is None or self.repository.task_exists_by_hash(task.prompt_hash):
            logger.info("generated task discarded for %s (null or duplicate)", generator.model_id)
            return
        generator.tasks_generated += 1
        generator.updated_at = datetime.now(UTC)
        self.repository.upsert_model_state(generator)
        self.repository.queue_task(task)
        logger.info("queued generated task %s from %s in domain %s", task.task_id, generator.model_id, task.primary_domain)

    async def _collect_bid(self, model: ModelState, task: Task, bootstrap: bool) -> Bid | None:
        template_name = "bidder_bootstrap.txt" if bootstrap else "bidder_production.txt"
        prompt = load_prompt(template_name).format(
            task_prompt=task.prompt,
            primary_domain=task.primary_domain,
            domain_quality=f"{model.mean_quality_for_domain(task.primary_domain):.2f}",
            domain_count=model.domain_task_counts.get(task.primary_domain, 0),
            calibration_score=f"{model.calibration_score:.2f}",
            recent_bid_mean=f"{model.stock_price:.2f}",
            recent_quality_mean=f"{model.mean_quality_for_domain(task.primary_domain):.2f}",
        )
        system_prompt = "You estimate expected task quality. Output only JSON."
        try:
            response = await self._provider_for(model).chat(
                model=model.api_model,
                system_prompt=system_prompt,
                user_prompt=prompt,
                timeout=self.settings.request_timeout,
                max_tokens=450,
                temperature=0.2,
            )
        except Exception as exc:
            model.timeout_count += 1
            model.updated_at = datetime.now(UTC)
            self.repository.upsert_model_state(model)
            logger.warning("bid failed for %s on task %s: %s", model.model_id, task.task_id, exc)
            return None
        parsed = parse_json_payload(response.content)
        if parsed.data is None:
            model.null_bid_count += 1
            model.updated_at = datetime.now(UTC)
            self.repository.upsert_model_state(model)
            logger.warning("bid parse failed for %s on task %s", model.model_id, task.task_id)
            return None
        payload = parsed.data
        bid = Bid(
            bid_id=new_id("bid"),
            task_id=task.task_id,
            model_id=model.model_id,
            confidence=clamp_score(payload.get("confidence"), fallback=0.0),
            domain_tags=normalize_domain_tags(payload.get("domain_tags")),
            rationale=str(payload.get("rationale") or "[unavailable]"),
            parse_status=parsed.status,
            calibration_weight=model.calibration_score,
        )
        logger.info(
            "bid accepted | model=%s task=%s confidence=%.3f parse=%s",
            model.model_id,
            task.task_id,
            bid.confidence,
            bid.parse_status,
        )
        return bid

    async def _execute_task(self, model: ModelState, task: Task) -> tuple[str, str]:
        prompt = load_prompt("executor.txt").format(task_prompt=task.prompt)
        try:
            response = await self._provider_for(model).chat(
                model=model.api_model,
                system_prompt="You complete tasks directly.",
                user_prompt=prompt,
                timeout=self.settings.request_timeout,
                max_tokens=1200,
                temperature=0.3,
            )
        except Exception as exc:
            logger.warning("execution failed for %s on task %s: %s", model.model_id, task.task_id, exc)
            return "", f"ERROR: {exc}"
        text = response.content.strip()
        if not text:
            logger.info("execution refusal/empty output | model=%s task=%s", model.model_id, task.task_id)
            return "", "REFUSAL"
        logger.info("execution complete | model=%s task=%s chars=%s", model.model_id, task.task_id, len(text))
        return text, "COMPLETE"

    async def _evaluate(self, evaluator: ModelState, task: Task, response_text: str) -> EvaluationScore | None:
        prompt = load_prompt("evaluator.txt").format(
            task_prompt=task.prompt,
            response_text=response_text,
            accuracy_weight=task.rubric.accuracy,
            usefulness_weight=task.rubric.usefulness,
            clarity_weight=task.rubric.clarity,
        )
        try:
            response = await self._provider_for(evaluator).chat(
                model=evaluator.api_model,
                system_prompt="You are a careful evaluator. Output only JSON.",
                user_prompt=prompt,
                timeout=self.settings.request_timeout,
                max_tokens=700,
                temperature=0.1,
            )
        except Exception as exc:
            evaluator.timeout_count += 1
            evaluator.updated_at = datetime.now(UTC)
            self.repository.upsert_model_state(evaluator)
            logger.warning("evaluation failed for %s on task %s: %s", evaluator.model_id, task.task_id, exc)
            return None
        parsed = parse_json_payload(response.content)
        if parsed.data is None:
            logger.warning("evaluation parse failed for %s on task %s", evaluator.model_id, task.task_id)
            return None
        payload = parsed.data
        clarity = clamp_score(payload.get("clarity_score"), 0.0)
        usefulness = clamp_score(payload.get("usefulness_score"), 0.0)
        accuracy = clamp_score(payload.get("accuracy_score"), 0.0)
        composite = (
            (clarity * task.rubric.clarity)
            + (usefulness * task.rubric.usefulness)
            + (accuracy * task.rubric.accuracy)
        )
        evaluation = EvaluationScore(
            evaluator_model_id=evaluator.model_id,
            clarity_score=clarity,
            usefulness_score=usefulness,
            accuracy_score=accuracy,
            clarity_reasoning=str(payload.get("clarity_reasoning") or ""),
            usefulness_reasoning=str(payload.get("usefulness_reasoning") or ""),
            accuracy_reasoning=str(payload.get("accuracy_reasoning") or ""),
            composite_score=composite,
            evaluator_reputation_snapshot=evaluator.evaluator_reputation,
            parse_status=parsed.status,
        )
        logger.info(
            "evaluation accepted | evaluator=%s task=%s composite=%.3f parse=%s",
            evaluator.model_id,
            task.task_id,
            evaluation.composite_score,
            evaluation.parse_status,
        )
        return evaluation

    def _bootstrap_mode(self, models: list[ModelState]) -> bool:
        return any(model.ipo_rounds_completed < self.settings.bootstrap_rounds for model in models)

    async def run_one_round(self) -> RoundResult:
        self.bootstrap()
        models = self.repository.list_model_states()
        if len(models) < 4:
            raise RuntimeError("At least four active models are required")
        await self._maybe_generate_task(models)
        self._ensure_task_supply(models)
        task = self.repository.reserve_next_task()
        if task is None:
            raise RuntimeError("No task is available")

        bootstrap = self._bootstrap_mode(models)
        cycle_number = self.repository.latest_cycle_number() + 1
        logger.info(
            "round start | cycle=%s task=%s domain=%s source=%s bootstrap=%s",
            cycle_number,
            task.task_id,
            task.primary_domain,
            task.source,
            bootstrap,
        )
        bid_results = await asyncio.gather(*(self._collect_bid(model, task, bootstrap) for model in models))
        bids = [bid for bid in bid_results if bid is not None]
        if len(bids) < 2:
            task.status = "QUEUED"
            self.repository.update_task(task)
            logger.error("round aborted | cycle=%s task=%s reason=not_enough_bids", cycle_number, task.task_id)
            raise RuntimeError("Not enough valid bids to run a round")

        by_model = {model.model_id: model for model in models}
        for bid in bids:
            sample, score = sample_allocation_score(by_model[bid.model_id], bid.confidence, bootstrap)
            bid.thompson_sample = sample
            bid.allocation_score = score
            logger.info(
                "allocation candidate | cycle=%s model=%s sample=%.3f score=%.3f confidence=%.3f",
                cycle_number,
                bid.model_id,
                sample,
                score,
                bid.confidence,
            )
        selected_bid = random.choice(bids) if bootstrap else max(bids, key=lambda item: item.allocation_score or 0.0)
        selected_bid.was_selected = True
        executor = by_model[selected_bid.model_id]
        logger.info(
            "executor selected | cycle=%s model=%s confidence=%.3f score=%.3f",
            cycle_number,
            executor.model_id,
            selected_bid.confidence,
            selected_bid.allocation_score or 0.0,
        )
        response_text, outcome = await self._execute_task(executor, task)
        evaluators = [model for model in models if model.model_id != executor.model_id]
        evaluation_results = await asyncio.gather(*(self._evaluate(model, task, response_text) for model in evaluators))
        evaluations = [item for item in evaluation_results if item is not None]
        if len(evaluations) < self.settings.min_evaluators:
            task.status = "QUEUED"
            self.repository.update_task(task)
            logger.error("round aborted | cycle=%s task=%s reason=not_enough_evaluators", cycle_number, task.task_id)
            raise RuntimeError("Not enough evaluator responses to score the round")

        council_quality, quality_std = weighted_quality_score(evaluations)
        objective_score = objective_anchor_score(task, response_text)
        quality_score = council_quality if objective_score is None else objective_score
        bid_error = update_executor_state(executor, task, quality_score, selected_bid.confidence)
        executor.updated_at = datetime.now(UTC)
        self.repository.upsert_model_state(executor)
        logger.info(
            "round scored | cycle=%s executor=%s quality=%.3f council=%.3f objective=%s brier=%.3f std=%.3f",
            cycle_number,
            executor.model_id,
            quality_score,
            council_quality,
            "none" if objective_score is None else f"{objective_score:.3f}",
            bid_error,
            quality_std,
        )

        for evaluation in evaluations:
            evaluator = by_model[evaluation.evaluator_model_id]
            update_evaluator_reputation(evaluator, evaluation.composite_score, objective_score)
            evaluator.updated_at = datetime.now(UTC)
            self.repository.upsert_model_state(evaluator)

        task.status = "COMPLETE"
        self.repository.update_task(task)
        result = RoundResult(
            round_id=new_id("round"),
            cycle_number=cycle_number,
            task=task.to_dict(),
            executor_model_id=executor.model_id,
            bid=selected_bid.to_dict(),
            execution_response=response_text,
            execution_outcome=outcome,
            quality_score=quality_score,
            quality_score_std=quality_std,
            evaluator_count=len(evaluations),
            brier_score=bid_error,
            is_ground_truth_round=task.is_ground_truth,
            objective_score=objective_score,
            evaluations=[item.to_dict() for item in evaluations],
            provisional=bootstrap,
        )
        self.repository.save_round_result(result)
        self.repository.save_market_snapshot(self.market_summary())
        logger.info(
            "round complete | cycle=%s executor=%s price=%.3f calibration=%.3f provisional=%s",
            cycle_number,
            executor.model_id,
            executor.stock_price,
            executor.calibration_score,
            bootstrap,
        )
        return result

    async def run_batch(self, count: int) -> list[RoundResult]:
        results: list[RoundResult] = []
        for _ in range(count):
            results.append(await self.run_one_round())
        return results

    def market_summary(self) -> dict[str, Any]:
        models = sorted(self.repository.list_model_states(), key=lambda item: item.stock_price, reverse=True)
        rounds = self.repository.list_recent_rounds(limit=20)
        return {
            "created_at": datetime.now(UTC).isoformat(),
            "pool_relative": True,
            "models": [state.to_dict() for state in models],
            "recent_rounds": rounds,
            "task_count": len(self.repository.list_tasks(limit=200)),
            "provisional": self._bootstrap_mode(models),
        }
