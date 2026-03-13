from stock_bench.market import brier_score, weighted_quality_score
from stock_bench.models import EvaluationScore


def test_brier_score_is_bounded() -> None:
    assert round(brier_score(0.9, 0.1), 6) == 0.64
    assert 0.0 <= brier_score(0.1, 0.9) <= 1.0


def test_weighted_quality_score_uses_reputation() -> None:
    scores = [
        EvaluationScore(
            evaluator_model_id="a",
            clarity_score=0.9,
            usefulness_score=0.9,
            accuracy_score=0.9,
            clarity_reasoning="ok",
            usefulness_reasoning="ok",
            accuracy_reasoning="ok",
            composite_score=0.9,
            evaluator_reputation_snapshot=1.0,
        ),
        EvaluationScore(
            evaluator_model_id="b",
            clarity_score=0.1,
            usefulness_score=0.1,
            accuracy_score=0.1,
            clarity_reasoning="ok",
            usefulness_reasoning="ok",
            accuracy_reasoning="ok",
            composite_score=0.1,
            evaluator_reputation_snapshot=0.2,
        ),
    ]
    mean, std = weighted_quality_score(scores)
    assert mean > 0.5
    assert std >= 0.0
