import asyncio

from stock_bench.models import RoundResult
from stock_bench.orchestrator import MarketOrchestrator


def _dummy_round(cycle_number: int) -> RoundResult:
    return RoundResult(
        round_id=f"round_{cycle_number}",
        cycle_number=cycle_number,
        task={"task_id": f"task_{cycle_number}", "prompt": "test prompt"},
        executor_model_id="model-a",
        bid={"confidence": 0.5},
        execution_response="ok",
        execution_outcome="COMPLETE",
        quality_score=0.5,
        quality_score_std=0.1,
        evaluator_count=3,
        brier_score=0.0,
        is_ground_truth_round=False,
        objective_score=None,
        evaluations=[],
    )


def test_run_sweep_collects_results_and_failures(monkeypatch) -> None:
    orchestrator = MarketOrchestrator.__new__(MarketOrchestrator)
    calls = {"count": 0}

    async def fake_run_one_round(*, randomize_task: bool = False):
        calls["count"] += 1
        assert randomize_task is True
        if calls["count"] == 2:
            raise RuntimeError("boom")
        return _dummy_round(calls["count"])

    monkeypatch.setattr(orchestrator, "run_one_round", fake_run_one_round)

    summary = asyncio.run(orchestrator.run_sweep(3))

    assert summary["requested"] == 3
    assert summary["completed"] == 2
    assert summary["failed"] == 1
    assert summary["errors"] == ["boom"]
    assert len(summary["rounds"]) == 2