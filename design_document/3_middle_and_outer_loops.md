# Part III: The Middle and Outer Loops

[Back to index](readme.md) · [Previous: Part II](2_inner_loop.md) · [Next: Part IV](4_operations_and_security.md)

---

## 11. The Market Agent and Outer Loop

### 11.1 Scope and Constraints

The market agent is a deterministic monitoring algorithm, not a free-form LLM agent. This distinction is essential. A free-form LLM agent making autonomous decisions about market structure would itself be an unverified participant influencing the prices it is supposed to measure. The market agent runs a defined set of statistical algorithms on committed data, produces structured reports, and takes a small set of bounded automatic actions. Every other recommendation requires human review.

The market agent runs every M = 200 inner-loop cycles. Its two automatic actions are: (1) suspend a model that has generated tasks containing prompt injection patterns at a rate exceeding the INJECTION_RATE_THRESHOLD (three triggers in 100 generated tasks); and (2) trigger an IPO sprint reinitialisation for a model whose CUSUM drift score exceeds 2 × CUSUM_THRESHOLD, indicating a severe and prolonged quality shift.

### 11.2 CUSUM Drift Detection — Corrected Algorithm

Version 2.0 described CUSUM with `CUSUM_TARGET = 0.0` and "measuring change from current mean," which is not a coherent description of how the algorithm works. CUSUM requires a fixed target, not a moving one, and the accumulators are reset periodically. Here is the correct procedure.

At each outer-loop run (every M rounds), for each ACTIVE model:

1. Compute the rolling mean quality score over the last M rounds for this model: `baseline = mean(q_i for the last M rounds where model was executor)`. If the model has fewer than 10 execution rounds in the last M outer-loop rounds, skip drift detection for this model.

2. Reset the CUSUM accumulators to zero: `cusum_pos = 0`, `cusum_neg = 0`.

3. Process the next M rounds (the *current* outer-loop window) as they complete, accumulating:

```python
cusum_pos = max(0, cusum_pos + (q - baseline - CUSUM_SLACK))
cusum_neg = max(0, cusum_neg + (baseline - q - CUSUM_SLACK))
```

4. At the end of the M-round window, if `cusum_pos > CUSUM_THRESHOLD`, flag an upward drift (model may have improved). If `cusum_neg > CUSUM_THRESHOLD`, flag a downward drift (model may have degraded). Record direction, magnitude, and first round where the threshold was breached.

In practice, the outer loop does not "wait" for the window to complete — it fires every M rounds and evaluates the completed data up to that point. The implementation should track a rolling CUSUM that resets at each outer-loop run. The direction and magnitude of breach (how far above threshold the accumulator went) determines whether the market agent auto-triggers a reinitialisation or only flags for human review: auto-trigger at `cusum_neg > 2 × CUSUM_THRESHOLD` (severe degradation); flag for human review at `CUSUM_THRESHOLD < cusum_neg ≤ 2 × CUSUM_THRESHOLD`.

With CUSUM_SLACK = 0.05 and CUSUM_THRESHOLD = 5.0, the algorithm detects a sustained shift of 2 × CUSUM_SLACK = 0.10 in mean quality after approximately CUSUM_THRESHOLD / CUSUM_SLACK = 100 rounds. This sensitivity is appropriate for detecting API provider silent updates, which typically shift model quality by 0.05–0.15 on this scale.

### 11.3 Concentration Monitoring

The Herfindahl-Hirschman Index is computed as `HHI = sum(s_i² for all models)` where s_i is model i's share of task allocations over the last M rounds. At HHI > HHI_HIGH_THRESHOLD = 0.35, a HIGH_CONCENTRATION flag is raised. At HHI < HHI_LOW_THRESHOLD = 0.05 (with N > 4 models), a LOW_CONCENTRATION flag is raised.

High concentration causes: genuinely dominant model (acceptable but confirm), broken Thompson Sampling (check implementation), or an overconfident model that gamed allocation before calibration discounting kicked in (investigate if new model recently entered). Low concentration causes: insufficient differentiation between models, overly aggressive exploration, or very early operation before priors accumulate (expected during the first 100 rounds and should not trigger a flag then).

### 11.4 Generator Health and Cost Monitoring

The market agent tracks the 10th percentile of discriminativeness scores for recently completed generated tasks. If this drops below DISCRIMINATIVENESS_MIN = 0.04 for two consecutive outer-loop cycles, a TASK_QUALITY_DEGRADATION flag is raised. This signals that the generator pool is producing tasks too easy for the current model pool, and difficulty parameters should be increased.

The market agent also computes per-model **length-quality correlation** over the last M rounds: the Pearson correlation between each executor's response token count and its received quality score. If this exceeds 0.5 for any model, a LENGTH_BIAS_CORRELATION flag is raised — a signal that evaluators may be rewarding verbosity rather than quality for that model's responses.

Additionally, the market agent computes the **per-round API call count and estimated cost** and writes cumulative cost to the market report. This is the only place in the system where cost is tracked; see Section 14 for the cost model.

### 11.5 Market Report Contents

Generated every M rounds: timestamp and cycle count; stock prices with 95% CI for all models; per-domain leaderboards (top 3 models per domain); calibration rankings; evaluator reputation rankings; latency rankings; cumulative API cost estimate; any active anomaly flags with severity and recommended action; task domain distribution over the last M rounds; discriminativeness p10 and median; top 5 most disagreement-inducing tasks (flagged for human review); memorisation signal (performance gap between known-benchmark and novel ground-truth tasks); and the CUSUM status for each model.
