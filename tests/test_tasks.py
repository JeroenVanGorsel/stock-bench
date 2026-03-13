from stock_bench.tasks import parse_generated_task


def test_parse_generated_task_returns_task() -> None:
    task = parse_generated_task(
        '{"prompt": "Explain CAP theorem simply.", "domain_tags": ["code_and_systems"], "primary_domain": "code_and_systems", "difficulty": 0.4, "importance": 1.0}',
        generator_model_id="g1",
    )
    assert task is not None
    assert task.primary_domain == "code_and_systems"
