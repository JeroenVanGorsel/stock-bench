from pathlib import Path

from stock_bench.models import ModelState
from stock_bench.storage import SQLiteRepository
from stock_bench.tasks import seed_tasks


def test_repository_round_trip(tmp_path: Path) -> None:
    repository = SQLiteRepository(str(tmp_path / "test.db"))
    repository.upsert_model_state(
        ModelState(
            model_id="m1",
            display_name="Model 1",
            provider="openrouter",
            api_model="openai/gpt-4.1-mini",
        )
    )
    tasks = seed_tasks()
    repository.queue_task(tasks[0])

    assert repository.get_model_state("m1") is not None
    assert repository.reserve_next_task() is not None
