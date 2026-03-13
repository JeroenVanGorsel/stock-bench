"""Seed tasks and lightweight task generation."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any

from .config import DOMAIN_TAXONOMY
from .models import Task, TaskRubric, new_id
from .parsing import ParsedPayload, clamp_score, normalize_domain_tags, parse_json_payload
from .prompt_loader import load_prompt
from .providers.base import ProviderClient


def normalize_prompt(prompt: str) -> str:
    return " ".join(prompt.lower().split())


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(normalize_prompt(prompt).encode("utf-8")).hexdigest()


def seed_tasks() -> list[Task]:
    base = [
        Task(
            task_id=new_id("task"),
            prompt="Return only the year of the Battle of Hastings.",
            domain_tags=["factual_synthesis"],
            primary_domain="factual_synthesis",
            difficulty=0.1,
            importance=1.0,
            is_ground_truth=True,
            ground_truth_answer="1066",
            source="ground_truth_seed",
        ),
        Task(
            task_id=new_id("task"),
            prompt="Give exactly three bullet points explaining why version control matters for a software team.",
            domain_tags=["instruction_following"],
            primary_domain="instruction_following",
            difficulty=0.25,
            importance=1.0,
            source="seed",
        ),
        Task(
            task_id=new_id("task"),
            prompt="Explain the difference between a queue and a stack with one concrete example for each.",
            domain_tags=["code_and_systems"],
            primary_domain="code_and_systems",
            difficulty=0.3,
            importance=1.1,
            source="seed",
        ),
        Task(
            task_id=new_id("task"),
            prompt="Write a concise argument for and against remote work, then state a balanced conclusion.",
            domain_tags=["ethical_nuanced_judgment"],
            primary_domain="ethical_nuanced_judgment",
            difficulty=0.45,
            importance=1.0,
            source="seed",
        ),
        Task(
            task_id=new_id("task"),
            prompt="Rewrite this sentence in a more persuasive tone without changing its meaning: We should update the onboarding guide.",
            domain_tags=["creative_rhetorical"],
            primary_domain="creative_rhetorical",
            difficulty=0.35,
            importance=0.9,
            source="seed",
        ),
    ]
    return [replace(task, prompt_hash=prompt_hash(task.prompt)) for task in base]


def parse_generated_task(text: str, generator_model_id: str) -> Task | None:
    parsed = parse_json_payload(text)
    if parsed.data is None:
        return None
    data = parsed.data
    prompt = str(data.get("prompt", "")).strip()
    if not prompt:
        return None
    domain_tags = normalize_domain_tags(data.get("domain_tags"))
    primary_domain = str(data.get("primary_domain") or domain_tags[0]).strip()
    if primary_domain not in DOMAIN_TAXONOMY:
        primary_domain = domain_tags[0]
    task = Task(
        task_id=new_id("task"),
        prompt=prompt,
        domain_tags=domain_tags,
        primary_domain=primary_domain,
        difficulty=clamp_score(data.get("difficulty"), fallback=0.5),
        importance=max(0.5, min(2.0, float(data.get("importance", 1.0)))),
        rubric=TaskRubric(),
        is_ground_truth=False,
        generator_model_id=generator_model_id,
        source="dynamic_generation",
        prompt_hash=prompt_hash(prompt),
    )
    return task


async def generate_task(client: ProviderClient, api_model: str, generator_model_id: str, timeout: float) -> Task | None:
    system_prompt = "You create benchmark tasks. Output only JSON."
    user_prompt = load_prompt("generator.txt")
    response = await client.chat(
        model=api_model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout=timeout,
        max_tokens=700,
        temperature=0.7,
    )
    return parse_generated_task(response.content, generator_model_id)
