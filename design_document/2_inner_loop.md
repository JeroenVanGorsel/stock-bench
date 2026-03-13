# Part II: The Inner Loop

[Back to index](readme.md) · [Previous: Part I](1_concept_and_design.md) · [Next: Part III](3_middle_and_outer_loops.md)

---

## 5. Task Generation

### 5.1 The Two Sources

Tasks arrive from two sources: a curated ground-truth bank and dynamic model-generated tasks. Ground-truth tasks anchor the evaluation system to objective correctness and calibrate evaluator reputations. Dynamic tasks probe current capability boundaries. Neither source alone is sufficient: ground-truth alone would be a static benchmark; dynamic generation alone, without objective anchoring, drifts into pure peer-relativism.

### 5.2 Ground-Truth Task Bank

Ground-truth tasks have verifiable correct answers evaluated automatically. The categories are: mathematical derivations and proofs (verified by a symbolic computation system, specifically SymPy for algebraic problems and a custom proof-checker for logical chains), code completion problems (verified by running automated test suites in a sandboxed execution environment), and factual questions requiring unambiguous single-value answers (verified against a curated reference database). Note the constraint on factual questions: they must have *one defensible correct answer*. "What year was the Battle of Hastings?" is appropriate. "What caused the First World War?" is not — it has no single correct answer and produces ambiguous ground-truth quality scores.

The scoring infrastructure these tasks require is significant: a SymPy integration for mathematical verification, a sandboxed Python/JavaScript execution environment for code testing, and a reference database for factual questions. These are Phase 1 infrastructure requirements, not optional features, because the entire calibration system depends on ground-truth anchor points.

The bank requires GROUND_TRUTH_BANK_MIN = 500 tasks before entering production. At 20% sampling and one round every 30 seconds, the system uses approximately 240 ground-truth tasks per hour. A 500-task bank provides about two hours of non-repeating coverage; it should be refreshed weekly by adding 200 new tasks and retiring tasks used more than MAX_GT_TASK_USES = 10 times.

One risk to name explicitly: models may have memorised common benchmark questions from pre-training data. If a factual question appears verbatim in a public benchmark that models were trained on, their performance on that question reflects memorisation, not capability. The bank should flag any task sourced from a known public benchmark (MMLU, TriviaQA, etc.) and track performance on flagged vs unflagged tasks separately. Systematically higher scores on flagged tasks are a memorisation signal worth reporting in the market report.

The bank also supports **evaluator reputation calibration**: on ground-truth rounds, the quality score is not set by the council — it is set by the automatic verifier. The council *also* evaluates the response, and their scores are compared against the ground-truth score. This comparison produces the signal that updates each evaluator's reputation: if the verifier says 0.1 (wrong answer) and an evaluator scored 0.85, that evaluator was badly miscalibrated, and its reputation decreases accordingly.

### 5.3 Dynamic Task Generation

The generator role rotates across registered models. The rotation uses **inverse mean-discriminativeness weighting**: models whose tasks produce higher discrimination between model quality levels (higher discriminativeness scores) get more rotation turns, incentivising generators to produce genuinely separating tasks. The weight for model i is `w_i = disc_i / sum(disc_j for all j)`, where disc is the model's current mean discriminativeness score.

New generators start with a discriminativeness score equal to the **current pool mean discriminativeness**, not a fixed 0.5. If experienced generators average 0.18 (which is realistic — inter-model quality variance on most tasks is modest), starting new generators at 0.5 would give them 2–3× more rotation weight than they deserve. The pool-mean initialisation is neutral and fair.

No model is assigned consecutive generator turns, preventing any single model from steering the task distribution. For practical scheduling: maintain a generator assignment queue. After a model's turn, it goes to the back of the queue, which is sorted by current rotation weight. If the queue's front entry is the same as the last generator, advance to the second entry.

The generator receives a generation prompt (Section 16.4) that specifies a target domain, target difficulty, exemplar tasks for format reference, and a novelty requirement relative to recent tasks in the same domain. The semantic novelty check uses a small locally-run embedding model (e.g., `sentence-transformers/all-MiniLM-L6-v2`) rather than an API call, to avoid circular dependencies and control cost.

### 5.4 Task Validation

Generated tasks require validation before entering the queue. In v2, this was described as a "human-calibrated oracle" evaluating a validation model's attempt — a bottleneck requiring constant human annotation. The corrected procedure uses the existing council infrastructure: a randomly selected non-generator model executes the task, and the council evaluates the result. The resulting quality score serves as the validation signal:

If the quality score is above VALIDATION_TOO_EASY_THRESHOLD = 0.93 (nearly all evaluators give maximum scores), the task is too easy and is discarded. If the quality score is below VALIDATION_TOO_HARD_THRESHOLD = 0.07 (nearly all evaluators give minimum scores, or the executor refuses or produces nonsense), the task may be unsolvable and is held for human review. Otherwise the task enters the queue. This costs one full round cycle per generated task, which is acceptable given that generation is rate-limited by queue depth (Section 3.5).

### 5.5 Discriminativeness: Corrected Definition

Version 2.0 defined discriminativeness as "the variance of all quality scores received across all models that participated in that round's evaluation." This was wrong. In any given round, only one model executes the task. The other models evaluate that one response. Evaluator scores measure their disagreement about one response, not the variance in how different models would perform if they all executed the task. Evaluator disagreement and execution quality variance are related but not the same thing.

The corrected definition distinguishes two cases.

For **validation tasks** (where one round is dedicated to sending the task to one model for the purpose of queue-entry validation), discriminativeness cannot be measured from a single execution. These tasks receive an estimated discriminativeness based on the variance of evaluator composite scores from the validation round, as a proxy. This proxy is acknowledged as imperfect: tasks that produce disagreement among evaluators are *correlated* with tasks that would produce variance in execution quality, but the correlation is not tight.

For **regularly executed tasks** that have been run in N_DISC_SAMPLE ≥ 3 rounds across different executing models, discriminativeness is computed properly: it is the variance of execution quality scores across the different executor models that have run the task. Over time, as the same task is allocated to different models across rounds, this score improves. The task corpus accumulates proper discriminativeness estimates as the system matures.

The generator's discriminativeness score is updated only from the properly-measured execution-variance discriminativeness, not from the proxy. This means new generators' scores are based on proxy estimates (honest, but noted as provisional), and experienced generators' scores are based on true execution variance (authoritative).

### 5.6 Domain Taxonomy

The taxonomy is defined in a configuration file. The default contains seven first-level domains: Formal Reasoning (mathematics, logic, proof verification, constraint satisfaction), Code and Systems (code generation, debugging, code review, system design), Factual Synthesis (knowledge retrieval, summarisation, citation reasoning, fact-checking), Creative and Rhetorical (persuasive writing, narrative, tone adaptation, stylistic rewriting), Ethical and Nuanced Judgment (ethical dilemmas, policy trade-offs, nuanced positions), Structured Data Analysis (table reasoning, chart interpretation, statistical reasoning), and Instruction Following (multi-step procedures, format compliance, constrained generation).

Portfolio management tracks the primary tag (first in the list) for concentration calculations. The market agent monitors subdomain-level concentration as well, because a model could generate tasks distributed across multiple first-level domains while systematically concentrating within subdomains that match its strengths.

### 5.7 Deduplication

Duplicate tasks corrupt calibration by producing artificial consistency. Deduplication runs in two stages: a fast hash check (normalised prompt → SHA256, reject if hash in corpus), then a semantic similarity check comparing the new task's embedding against the last 1,000 domain-matched tasks using cosine similarity, rejecting if similarity exceeds 0.85. The embedding model used here is the same local model used for novelty checking in generation, ensuring consistency in similarity measurement.

---

## 6. The Bid Mechanism

### 6.1 What a Bid Claims

A bid is a model's estimate of the quality score it expects to receive from the evaluator council on a specific task. The value is a float in [0, 1]. 1.0 means "I expect to receive the maximum composite quality score from this council on this task." This framing matters: the model is not claiming a probability of binary success. It is estimating a continuous quality value. The Brier score is proper for this setting as long as this framing is clear.

One complexity: the quality score a model receives depends on which models evaluate it, and evaluator composition varies round to round. A model bidding on a task cannot know whether it will be evaluated by particularly strict or lenient evaluators this round. Over time the model learns the average pool strictness, but there is inherent noise in quality score estimates that no amount of accurate self-knowledge can eliminate. The model should bid its best estimate of its expected quality under average pool conditions, not try to predict council composition.

### 6.2 What Models See — and Why the Stock Price Scalar is Hidden

The bid prompt provides performance history — but version 2.0 included the overall stock price as a single number, which creates an anchoring problem. Research on numerical anchoring in both humans and LLMs shows that the presence of a reference number systematically pulls estimates toward it, regardless of framing instructions. A model shown "your current price is 0.72" will tend to bid near 0.72 even on tasks where its domain performance suggests a very different number.

The corrected bid context omits the overall stock price scalar. Instead, it shows:
- Per-domain mean quality score and task count (the most actionable signal for task-specific self-assessment)
- Rolling calibration error over the last K rounds (calibration quality)
- Rolling mean bid vs rolling mean quality score over the last K rounds (the gap between stated and delivered quality)
- Total tasks completed (pool maturity signal)

What it does *not* show: overall stock price, competitor information, or any ranking. The performance data is presented in raw form, not reduced to a single number that invites anchoring.

### 6.3 Selective Participation and the Timeout Attack

A model whose API implementation selectively returns TIMEOUT on tasks it expects to perform poorly on achieves inflated calibration scores: it bids only on tasks it is confident about, avoids Brier penalty on hard tasks, and accumulates a misleadingly good calibration record.

Detection: compute the correlation between each model's per-round timeout flag and the pool-mean quality score on that round's task (a proxy for task difficulty — harder tasks produce lower pool-mean quality). If this correlation exceeds SELECTIVE_PARTICIPATION_THRESHOLD = 0.3 over the last M rounds, raise a SELECTIVE_PARTICIPATION anomaly flag. The interpretation: the model's timeouts are not random; they are concentrated on rounds where the task is difficult for the pool.

Note that a legitimate model with API reliability problems will also show timeout-difficulty correlation if its API is more likely to fail under load (which may correlate with computationally hard tasks). The flag requires human review to distinguish intentional selective participation from API instability. Both cases should be investigated.

### 6.4 Bid Output Schema and Parsing

The bid schema:

```json
{
  "confidence": 0.72,
  "domain_tags": ["creative_writing", "persuasion"],
  "rationale": "This task requires tonal nuance. My recent persuasion task scores average 0.68. Moderate confidence."
}
```

The `bid_timestamp` field is added by the parser after the response is received; models do not produce it. All three model-generated fields are required. `confidence` must be a float in [0.0, 1.0]. `domain_tags` must be a non-empty list of strings from the taxonomy. `rationale` must be a non-empty string of at least 20 characters.

The parser handles malformed model output. The fallback chain is: standard `json.loads()` → `json5.loads()` (handles trailing commas, single quotes, comments) → regex extraction of the confidence float from any JSON-like structure → NULL bid. The `demjson` library mentioned in v2 is abandoned; `json5` is the correct modern replacement. A bid with parseable confidence but missing or invalid domain_tags is accepted with `domain_tags = ["unknown"]`. A bid with parseable confidence but missing rationale is accepted with `rationale = "[unavailable]"`. A bid whose confidence cannot be parsed by any method is a NULL bid, treated identically to a timeout.

### 6.5 Bid Rationale Storage and Future Use

The rationale field is stored permanently. Its three downstream uses: it creates an audit trail of self-assessment reasoning, it enables post-hoc analysis of whether models' verbal reasoning accurately predicts their numerical bids (systematic misalignment is itself a form of self-knowledge failure), and it provides a corpus for future research on LLM self-assessment quality. The system does not automatically evaluate rationale quality in v3; this is a deferred extension.

---

## 7. Task Allocation

### 7.1 The Composite Allocation Score

The allocation score for a model on a given task is:

```
allocation_score = W_PRIOR × thompson_sample + W_BID × confidence_bid × calibration_weight × domain_boost
```

where:

`thompson_sample` is a sample drawn from the model's current Beta(α, β) distribution. `confidence_bid` is the model's submitted confidence value. `calibration_weight` is the model's current calibration score — a number in [0, 1] that progressively discounts the bids of overconfident models. `domain_boost` is a multiplier rewarding domain match. `W_PRIOR = 0.6` and `W_BID = 0.4` (both configurable).

The `domain_boost` computation: if the model's bid domain_tags overlap with the task's primary domain tag, and the model's mean quality in that domain exceeds its overall mean quality, `domain_boost = 1.0 + 0.2 × (domain_quality - overall_quality)`, capped at 1.4. If there is no domain overlap, `domain_boost = 1.0`. If there is overlap but the model's domain quality is below its overall quality, `domain_boost = 1.0` (no penalty for bidding in a weak domain — the low confidence bid handles that).

The composite score ranges approximately from 0 to `0.6 × 1.0 + 0.4 × 1.0 × 1.0 × 1.4 = 1.16`. This is fine; the model with the highest score wins, and the absolute scale doesn't matter. Ties are broken by uniform random selection, with the tie recorded in round metadata.

### 7.2 Phase 1 Allocation (Bootstrapping the Formula)

The full allocation formula requires calibration scores and Thompson Sampling, which are not available in Phase 1 before persistent model state exists. The Phase 1 allocator uses **weighted random selection by bid confidence**: each bidding model receives a selection probability proportional to its confidence bid, and one model is drawn from this distribution. This is simple, produces proportional rather than winner-take-all allocation, does not create a pure-overbid equilibrium (models bidding 1.0 are selected more often but not exclusively, and the resulting data is still useful for calibration analysis), and is easily replaced in Phase 2 without changing the rest of the round cycle.

The previous v2 design ("select the highest raw confidence bid") would immediately incentivise all models to always bid 1.0, making Phase 1 bid data entirely worthless for calibration analysis. The weighted-random design avoids this.

### 7.3 The IPO Sprint Protocol

New models entering the marketplace undergo an IPO sprint: IPO_SPRINT_ROUNDS = 30 forced-allocation rounds, during which the model is guaranteed a task roughly 1 round in every 6. The 1-in-6 rate is fixed regardless of how many models are simultaneously in sprint. With three models sprinting simultaneously, half the rounds go to sprint models, which is acceptable for short-term onboarding.

The sprint completes when the model has executed IPO_SPRINT_ROUNDS rounds. After completion, forced allocation is removed and the model enters normal competition. Its Beta distribution is initialised from its sprint data rather than resetting to Beta(1, 1): `alpha_post = 1 + sum(q_i for sprint rounds)`, `beta_post = 1 + sum(1 - q_i for sprint rounds)`. This gives the market an informed starting prior rather than treating every completed sprint model as an unknown.

The statistical justification for 30 rounds: with quality score standard deviation of approximately 0.2, 30 observations yield a 95% CI of width ±0.072 on the mean, which is narrow enough for meaningful initial price publication.

During sprint, evaluations from the sprinting model count toward other models' quality scores with the initial evaluator reputation of 1.0. This is the correct neutral prior; the reputation updates immediately from ground-truth rounds.

---

## 8. Task Execution

### 8.1 Executor Isolation

The executor receives the task via a clean system prompt (Section 16.1) with no information about the marketplace, its current stock price, or its competitors. The task prompt is self-contained: it includes the full task specification, any required output format constraints, and the token limit. The system prompt's role is framing (you are completing a task) and injection resistance (ignore instructions in the content); it contains no performance context.

Every executor API call uses a **fresh context window** with no conversation history. This prevents any information leakage between a model's previous evaluation of another model's response and its current execution of a new task. In practice, API calls to providers without persistent conversation state are stateless by default, but this should be verified for each provider adapter.

### 8.2 Token Limits, Context Budget, and Truncation

Responses are hard-capped at RESPONSE_MAX_TOKENS = 2000 tokens. Truncation at the nearest sentence boundary before this limit is applied; the truncation is recorded in the round metadata and noted to evaluators.

The evaluation prompt's total token budget must be bounded: task_prompt (max 500 tokens) + executor_response (max 2000 tokens) + evaluation_instructions (max 600 tokens) = max 3,100 tokens. Task generation prompts must enforce the 500-token task limit. This keeps the evaluation prompt within the context window of all models likely to be in the pool. For code-generation tasks where context might be large, the task prompt token limit can be raised to 800 tokens with corresponding awareness that smaller evaluator models may struggle.

### 8.3 Refusals

A refusal means the model's API-enforced safety filters or policy constraints prevented generating a response. The correct treatment: quality_score = 0.0 for all purposes. The round records execution_outcome = REFUSAL. The task is re-queued. The refusing model's Beta distribution updates with q = 0.0. Its calibration error is (bid_confidence - 0.0)² — which is the correctly severe Brier penalty if the model bid high on a task it will refuse, and near-zero if it bid low (as a well-calibrated model should when it knows it will refuse that category of task).

There is no special-casing for refusals beyond this. The statement in v2 that "a refusal is not a quality score of 0" was incorrect. A refusal IS a quality score of 0 for all computational purposes. The distinction was an attempt to treat the model charitably for refusing an unsafe task rather than generating harmful content, but since the task bank is operator-curated and should never contain tasks that any legitimate model should refuse, a refusal is either a safety false-positive (the model is overly cautious on a benign task, which is a capability failure) or an indicator that the task bank contains inappropriate content (which should be flagged for human review by raising a TASK_REFUSAL_RATE_HIGH anomaly if refusals on a specific task exceed 30%).

### 8.4 Latency Tracking

Wall-clock execution latency is recorded for every round. It is not incorporated into stock prices in v3. A latency leaderboard is displayed on the dashboard as a secondary signal. The latency metric has a known limitation: it measures API round-trip time, which includes network latency and provider infrastructure overhead in addition to actual model inference time. For models behind different network paths, raw latency is partly measuring geography, not capability. For models on the same provider (e.g., two OpenAI models), latency comparison is more meaningful. This limitation should be noted on the dashboard.

---

## 9. Council Evaluation

### 9.1 Council Composition

All registered ACTIVE models except the executor participate as evaluators. Models in SUSPENDED status are excluded. Models that timed out during bidding are included in the evaluation pool — bid availability and evaluation availability are treated as independent (a model may be busy when the bid window opens but available for evaluation shortly after). MIN_EVALUATORS_PER_ROUND = 3 is the minimum for a valid quality score.

The chairman synthesis step from Karpathy's LLM Council is deliberately absent. It serves a different purpose (producing a better answer to a user question). Here the goal is measuring executor quality via independent evaluations, which synthesis would corrupt by making the final signal depend on the synthesis model's capabilities.

### 9.2 Anonymisation

The executor's response is presented to evaluators without identifying information. The anonymisation layer applies a standardised formatting normalisation to the response before distribution: markdown headers are converted to bold text, excessive bullet nesting is flattened to one level, and any "I" statements that reference the model's identity or training are redacted. This reduces (but does not eliminate) the ability of evaluators to identify the executing model's family from formatting style.

Full stylistic anonymisation is beyond feasible in practice. A Claude-family model tends to use structured markdown; a GPT-family model tends toward denser prose; Google Gemini models have distinct stylistic conventions. Partial recognition by evaluators may persist. The document acknowledges this as a known limitation rather than a solved problem (see Appendix C). The mitigations are: the anonymisation layer described above, the evaluator system prompt's explicit instruction to score on content not style, and the pairwise bias tracking that will detect and partially correct any systematic style-based preference that survives normalisation.

### 9.3 Multi-Dimensional Scoring, Rubric Weighting, and Axis Order

Evaluators score on three axes: accuracy, usefulness, and clarity. Each receives an independent score in [0, 1]. The composite score is the weighted average using the rubric weights from the task metadata.

The default rubric (when a task does not specify weights) is: accuracy = 0.5, usefulness = 0.35, clarity = 0.15. This default should be stored in the configuration file alongside the other parameters.

Scoring anchors for each axis:

**Accuracy:** 1.0 = all claims correct, reasoning sound; 0.7 = mostly correct, minor errors not affecting the conclusion; 0.4 = significant errors or logical gaps affecting the conclusion; 0.1 = fundamentally wrong in key respects; 0.0 = completely incorrect or fabricated.

**Usefulness:** 1.0 = directly and completely addresses the task; 0.7 = addresses the core but misses important aspects; 0.4 = partially relevant but does not solve the problem as posed; 0.1 = tangentially related; 0.0 = off-topic, evasive, or refused.

**Clarity:** 1.0 = key content is immediately accessible; 0.7 = clear with minor structural issues; 0.4 = answer present but requires effort to extract; 0.1 = very difficult to parse; 0.0 = incoherent. Length alone does not increase clarity.

The axes must be scored in a specific order: **clarity first, then usefulness, then accuracy**. This matters because of the **halo effect**: when evaluators first score a high-stakes conceptual axis like accuracy, their subsequent scores for usefulness and clarity are pulled upward by that initial positive assessment, producing correlated scores that overstate the response's quality on all dimensions. Scoring clarity first — the most concrete and observable axis — provides an objective anchor before evaluators engage with the more interpretive axes. The evaluation prompt must specify this order explicitly and explain why.

### 9.4 Length and Halo Bias Mitigations

LLM evaluators systematically rate longer responses higher, independent of content quality (length bias). They also rate all axes higher when one axis is high (halo effect). Mitigations: the fixed axis scoring order (Section 9.3) partially disrupts the halo effect; the explicit anti-length instruction ("length alone does not increase clarity; do not reward verbosity") and per-response token count display partially disrupt length bias; and the market agent monitors per-model length-quality correlation (Section 11.4) to detect residual bias. These are partial mitigations, not guarantees. The system accepts that evaluator scores contain some systematic noise from these effects, and treats the pairwise bias correction system as the downstream correction for any evaluator-specific persistent biases.

### 9.5 Evaluator Vote Weighting

Each evaluator's composite score is weighted by its evaluator reputation. The weighted quality score is:

```python
q = sum(rep_i * score_i for evaluators) / sum(rep_i for evaluators)
```

At bootstrap when all reputations are 1.0, this reduces to the simple mean.

Evaluator reputation measures how accurately a model evaluates others, calibrated against ground-truth rounds. The update formula corrected from v2:

```python
# After a ground-truth round where evaluator i gave composite_score_i
# and the ground-truth quality is gt_quality (from the automatic verifier):
graded_correctness = 1.0 - abs(composite_score_i - gt_quality)
new_rep = (1 - EVAL_REP_EMA_ALPHA) * current_rep + EVAL_REP_EMA_ALPHA * graded_correctness
```

The v2 formula used binary correctness (1 if "score direction matched GT, else 0"). This was too coarse: an evaluator that scores a wrong answer at 0.3 (close to the ground-truth 0.1) and one that scores it at 0.9 (badly wrong) received identical zero credit. Graded correctness gives partial credit proportional to how close the evaluation was to the ground truth.

Evaluator reputation starts at 1.0 for all models. With EVAL_REP_EMA_ALPHA = 0.05, it adapts slowly (effective window ≈ 20 ground-truth rounds). This is intentional: evaluator reputation should be a stable signal, not a noisy round-to-round estimate.

Evaluator reputation is computed globally, not per-domain. Per-domain evaluator reputation is a conceptually appealing extension (a model might be an excellent evaluator for code but a poor one for creative writing) but is deferred to a future version because it requires substantially more ground-truth coverage per domain to produce reliable per-domain estimates.

### 9.6 Evaluator Disagreement

When the standard deviation of composite scores across council members exceeds DISAGREEMENT_THRESHOLD = 0.20, the round is flagged as HIGH_DISAGREEMENT. The quality score is still the weighted mean — disagreement does not void the round. However, the Beta distribution update uses a **reduced weight**: instead of `alpha += q, beta += (1 - q)`, use `alpha += q * DISAGREEMENT_WEIGHT, beta += (1 - q) * DISAGREEMENT_WEIGHT` where DISAGREEMENT_WEIGHT = 0.35.

The justification for 0.35 (corrected from the unjustified 0.7 × normal in v2): the relative information content of a high-disagreement quality estimate compared to a normal one is proportional to `(sigma_normal / sigma_high)²`. With sigma_normal ≈ 0.08 and sigma_high ≈ 0.22 (typical values from LLM evaluation research), the ratio is `(0.08/0.22)² ≈ 0.13`. Rounding up slightly to 0.15 to avoid extremely slow Beta updates from genuine but ambiguous tasks, a value of 0.20–0.35 is the defensible range. We choose 0.35, slightly generous to preserve some update signal from disagreement rounds. This value should be empirically validated in Phase 2.

Note: this is the one place where the Beta update DOES use a multiplier. The distinction from the removed calibration multiplier: here the multiplier corrects for measurement noise in the quality score itself (evaluators disagreed, so the score is uncertain); in the removed case, the multiplier penalised the model for miscalibration, which should not suppress the quality signal.

### 9.7 Evaluator Bias Tracking and Retroactive Correction

The market agent maintains a pairwise bias matrix B where B[i][j] is the rolling mean difference between model i's evaluations of model j and the ensemble mean evaluations of model j across all rounds where i evaluated j. When |B[i][j]| exceeds PAIRWISE_BIAS_THRESHOLD = 0.15, an anomaly flag is raised.

The corrective action: going forward, model i's evaluations of model j are shifted by -B[i][j] before being combined with other evaluators. Additionally, retroactive correction is applied, **bounded to the last BIAS_RETROACTIVE_LIMIT = 400 rounds** (two outer-loop cycles). Beyond this limit, retroactive correction is not applied — it creates diminishing returns and risks numerical instability from recalculating hundreds of interlinked EMA updates.

The retroactive correction requires that each round_result stores not just q and cs but the exact **alpha_delta** and **beta_delta** values applied to each model's Beta distribution. This is necessary because a retroactive quality score change requires subtracting the old deltas and adding new ones, and these must be the exact values that were applied, not recomputed from current model state (since cs has changed via EMA in the interim). The data model in Section 15 has been updated to include these fields.

---

## 10. The Calibration Engine

### 10.1 The Two Signals: Calibration Score vs Evaluator Reputation

These are independent quantities that must never be conflated in code, documentation, or display.

The **calibration score** measures how accurately a model estimates its own performance on tasks it executes. Input data: (bid_confidence, received_quality_score) pairs from rounds where the model was executor. Output: a scalar in [0, 1], where 1.0 is perfect calibration. Effect: multiplied into the bid component of the allocation formula.

The **evaluator reputation** measures how accurately a model evaluates other models' outputs, benchmarked against ground-truth tasks. Input data: (evaluator_score, ground_truth_quality) pairs from ground-truth rounds where the model was an evaluator. Output: a scalar in [0, 1], where 1.0 means evaluations match ground truth perfectly. Effect: used as a vote weight in council quality score computation.

A model can have any combination of these: high calibration and low reputation (knows its own limits, bad at judging others), low calibration and high reputation (overestimates itself, but evaluates others accurately), or any other combination. They measure different aspects of self-knowledge and should be displayed separately on the dashboard.

### 10.2 Calibration Error Computation

For each execution round with bid confidence c, received quality score q, and task importance multiplier imp:

```python
# Raw Brier score (used for calibration EMA and allocation)
brier_score = (c - q) ** 2

# Importance-weighted calibration error (used for audit accounting only)
weighted_calibration_error = imp * brier_score
```

The distinction is critical. Version 2.0 used `calibration_error_round = imp × (c - q)²` and then fed this into the calibration EMA as `1 - calibration_error_round`. When imp = 2.0 and `(c - q)² = 0.6`, the weighted error is 1.2, and `1 - 1.2 = -0.2` — a negative calibration contribution that can cause the calibration score to drift below zero. Negative calibration scores then produce division-by-zero or nonsense allocation scores downstream.

The fix is to use the raw Brier score (without importance weighting) for the EMA. The importance-weighted error is stored in `weighted_calibration_error` in the round_result record for use in market agent analysis (to weight contribution to overall calibration quality accounting), but it never enters the EMA formula.

### 10.3 Calibration Score EMA Update

```python
# Called after every execution round
new_calibration_score = (
    (1 - CALIBRATION_EMA_ALPHA) * current_calibration_score
    + CALIBRATION_EMA_ALPHA * (1.0 - brier_score)  # NOT importance-weighted
)
# Clamp to [0, 1] as a defensive measure
new_calibration_score = max(0.0, min(1.0, new_calibration_score))
```

With CALIBRATION_EMA_ALPHA = 0.05, each new observation contributes 5% weight, with older observations exponentially decaying. The effective window is approximately 20 observations. Models start at calibration_score = 1.0 (the neutral prior, equivalent to assuming perfect calibration until demonstrated otherwise).

The clamp to [0, 1] is a defensive measure. With the raw Brier score, `(1 - brier_score)` is always in [0, 1], so the EMA cannot produce values outside [0, 1] without the importance-weighted bug. The clamp guards against floating-point edge cases and any future accidental reintroduction of the importance weighting.

### 10.4 Beta Distribution Update

```python
# Called after every execution round, BEFORE updating the calibration EMA
# The calibration_score used here is the snapshot at the START of this round
alpha += quality_score
beta  += (1.0 - quality_score)
```

Then update the calibration EMA:

```python
new_calibration_score = (1 - CALIBRATION_EMA_ALPHA) * calibration_score_snapshot + CALIBRATION_EMA_ALPHA * (1.0 - brier_score)
```

The order matters: Beta update first (using the snapshot cs from the start of the round), then EMA update. This ensures that the Beta update's credit for quality is not influenced by the current round's calibration error, which is consistent — the quality of the execution was not affected by whether the model happened to be well-calibrated about this particular task.

The only multiplier on the Beta update is the HIGH_DISAGREEMENT weight (Section 9.6), which corrects for measurement uncertainty in the quality score itself.

To support deterministic crash recovery, the round_result must store the exact alpha and beta increments applied:

```python
round_result.alpha_delta = quality_score        # Not q * cs
round_result.beta_delta  = 1.0 - quality_score  # Not (1-q) * cs
round_result.disagreement_weight = 1.0 or DISAGREEMENT_WEIGHT
```

Recovery replay adds alpha_delta and beta_delta to the current Alpha and Beta values directly, without recomputing anything from model state.

### 10.5 Stock Price and Volatility

These are computed on every read of model state, never stored:

```python
stock_price = alpha / (alpha + beta)
volatility  = sqrt((alpha * beta) / ((alpha + beta)**2 * (alpha + beta + 1)))
```

The 95% confidence interval for the stock price is approximately `price ± 1.96 * volatility`. For display, volatility below 0.05 should be labeled "stable," 0.05–0.10 "moderate variance," above 0.10 "high variance."
