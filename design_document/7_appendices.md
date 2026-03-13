# Appendices

[Back to index](readme.md) · [Previous: Part VI](6_implementation.md)

---

## Appendix A: Configuration Parameters

All parameters below should be stored in a single configuration file. Defaults are chosen for a frontier-class pool of 5–10 models running at one round every 30 seconds. Adjust proportionally for different throughputs or pool compositions.

**POOL_MIN_SIZE = 4.** Minimum active models to enter production mode. Below this, boot in DEMO mode.

**INNER_LOOP_K = 50.** Cadence of middle-loop background job (every 50 inner-loop cycles). Not the calibration EMA window — the EMA updates every single round.

**OUTER_LOOP_M = 200.** Cadence of outer-loop market agent run.

**GROUND_TRUTH_FRACTION = 0.20.** Fraction of rounds drawing from the GT bank. Reduce to 0.10 after 5,000 rounds.

**GROUND_TRUTH_BANK_MIN = 500.** Minimum GT bank size before production mode.

**MAX_GT_TASK_USES = 10.** Retire GT tasks after this many executions.

**BID_TIMEOUT_SECONDS = 15.** Maximum wait for a model's bid response.

**EXECUTION_TIMEOUT_SECONDS = 60.** Maximum wait for the executor's response.

**EVALUATION_TIMEOUT_SECONDS = 15.** Maximum wait per evaluator.

**MIN_EVALUATORS_PER_ROUND = 3.** Minimum valid council size.

**RESPONSE_MAX_TOKENS = 2000.** Hard cap on executor response length.

**TASK_PROMPT_MAX_TOKENS = 500.** Hard cap on task prompt length. 800 for code tasks.

**IPO_SPRINT_ROUNDS = 30.** Sprint length before price publication.

**IPO_SPRINT_ALLOCATION_RATE = 6.** Sprint model receives 1 in every N rounds.

**CALIBRATION_EMA_ALPHA = 0.05.** EMA decay factor for calibration score. Effective window ≈ 20 observations.

**EVAL_REP_EMA_ALPHA = 0.05.** EMA decay factor for evaluator reputation.

**W_PRIOR = 0.6, W_BID = 0.4.** Allocation formula weights for Thompson sample vs bid term.

**DOMAIN_MAX_FRACTION = 0.30.** Maximum fraction of recent tasks from any first-level domain.

**SUBDOMAIN_MAX_FRACTION = 0.12.** Maximum fraction from any single subdomain.

**DOMAIN_MIN_FRACTION = 0.05.** Minimum fraction per first-level domain.

**QUEUE_MIN_DEPTH = 20.** Trigger task generation when queue drops below this.

**QUEUE_TARGET_DEPTH = 50.** Generate tasks until queue reaches this depth.

**QUEUE_BATCH_SIZE = 10.** Number of tasks generated per generation trigger.

**DEFAULT_RUBRIC = {accuracy: 0.50, usefulness: 0.35, clarity: 0.15}.** Default rubric weights.

**VALIDATION_TOO_EASY_THRESHOLD = 0.93.** Discard generated tasks scoring above this in validation.

**VALIDATION_TOO_HARD_THRESHOLD = 0.07.** Hold for human review tasks scoring below this.

**HHI_HIGH_THRESHOLD = 0.35.** Flag high allocation concentration.

**HHI_LOW_THRESHOLD = 0.05.** Flag unusually diffuse allocation.

**CUSUM_SLACK = 0.05.** Per-step allowance before CUSUM accumulates.

**CUSUM_THRESHOLD = 5.0.** Accumulator value triggering a drift flag.

**PAIRWISE_BIAS_THRESHOLD = 0.15.** Evaluator pair bias triggering anomaly flag.

**BIAS_RETROACTIVE_LIMIT = 400.** Maximum rounds to apply retroactive bias correction.

**DISAGREEMENT_THRESHOLD = 0.20.** Std dev threshold for HIGH_DISAGREEMENT flag.

**DISAGREEMENT_WEIGHT = 0.35.** Beta update multiplier for high-disagreement rounds.

**DISCRIMINATIVENESS_MIN = 0.04.** Minimum discriminativeness before TASK_QUALITY_DEGRADATION flag.

**SELECTIVE_PARTICIPATION_THRESHOLD = 0.3.** Timeout-difficulty correlation for SELECTIVE_PARTICIPATION flag.

**MAX_MODELS_PER_PROVIDER = 3.** Registration cap per provider.

**PROVIDER_CORRELATION_THRESHOLD = 0.80.** Same-provider evaluation correlation for evaluator exclusion.

**DAILY_COST_THRESHOLD_USD.** Operator-set daily cost alert threshold.

**TASK_IMPORTANCE_RANGE = (0.5, 2.0).** Allowed range for task importance.

**MEMORISATION_FLAG_THRESHOLD = 0.10.** Performance gap (flagged vs novel GT tasks) for MEMORISATION_SIGNAL flag.

---

## Appendix B: Glossary

**Alpha (α):** The "success weight" in a model's Beta distribution. Increases by the quality score q after each execution round.

**Beta (β):** The "failure weight" in a model's Beta distribution. Increases by (1 - q) after each execution round. Not to be confused with the CALIBRATION_EMA_ALPHA parameter.

**Brier Score:** The squared error (c - q)² between a confidence bid c and a received quality score q. A proper scoring rule: the bid that minimises expected Brier loss equals the model's true expected quality.

**Calibration Score:** A rolling metric measuring how accurately a model estimates its own execution quality. Computed as the exponential moving average of (1 - brier_score). Affects allocation via the W_BID term in the composite allocation formula.

**CUSUM:** Cumulative Sum algorithm. A sequential change detection procedure that accumulates deviations from a baseline and fires when accumulated deviation exceeds a threshold. Used here to detect silent model updates.

**Discriminativeness:** For a task: the variance of quality scores received by different executor models across multiple rounds — how well the task separates strong from weak models. For a generator model: the exponential moving average of its tasks' discriminativeness scores.

**Evaluator Reputation:** A rolling metric measuring how accurately a model evaluates others, benchmarked against ground-truth tasks. Computed as the EMA of graded correctness (`1 - |eval_score - gt_quality|`). Affects council vote weighting.

**HHI (Herfindahl-Hirschman Index):** Market concentration measure. Sum of squared allocation shares across all models. 1/N = perfect equality; 1.0 = monopoly.

**Inner Loop:** A single task cycle. Runs continuously.

**IPO Sprint:** The 30-round bootstrap period for a new model, during which it receives forced allocations to accumulate a prior before entering normal market competition.

**Middle Loop:** Calibration accounting. Runs every 50 inner-loop cycles as a background job.

**Outer Loop:** Market monitoring. Runs every 200 inner-loop cycles as a background job.

**Pool-Relative Price:** Stock prices are computed against the current evaluator council. Prices within one pool composition are comparable; prices across different pool compositions are not directly comparable.

**Proper Scoring Rule:** A loss function for probability estimates where reporting your true belief minimises expected loss. The Brier score is proper for both binary and continuous outcomes.

**Stock Price:** α / (α + β). The current best estimate of a model's mean execution quality as measured by the evaluator council.

**Thompson Sampling:** A Bayesian exploration strategy. At each allocation step, sample from each model's Beta distribution and select the model with the highest sample. Naturally balances exploitation of known-good models with exploration of uncertain ones.

**Volatility:** The standard deviation of a model's Beta distribution: `sqrt(αβ / ((α+β)² (α+β+1)))`. Measures uncertainty about the stock price estimate.

---

## Appendix C: Known Limitations

This system has been designed with care to address the problems that can be addressed. The following limitations are acknowledged as real and presently unsolved, not as design oversights but as honest constraints on what any peer-evaluation system can achieve.

**Anonymisation is best-effort.** The formatting normalisation layer reduces but does not eliminate evaluators' ability to identify which model family produced a given response. Stylistic fingerprints (sentence rhythm, hedging phrases, markdown patterns) persist through formatting normalisation. The pairwise bias tracking system is the main downstream correction for any systematic style preferences that survive. True stylistic anonymisation would require an LLM-based rewriting pass, which introduces a new dependency and its own biases.

**Quality scores are pool-relative.** The system measures quality as assessed by the current evaluator council, not against an external absolute standard. This is unavoidable in a peer-evaluation design. The ground-truth anchoring (20% of rounds) partially addresses this but does not eliminate pool-relativity for the 80% of dynamically generated rounds.

**LLMs may not respond to Brier incentives.** The proper scoring rule creates the right structure for incentivising honest self-assessment. Whether any specific LLM actually produces better-calibrated bids because of this structure, rather than because it was trained to produce calibrated-sounding outputs, is an empirical question the system can measure but cannot guarantee. The calibration scores the system produces are measurements of calibration under these conditions; they do not certify that the calibration extends to conditions outside the system.

**Discriminativeness proxy during early operation.** Before a generated task has been executed by three or more different models, its discriminativeness score is estimated from evaluator disagreement rather than execution variance. This proxy is positively correlated with true discriminativeness but noisy. Early generator discriminativeness scores are based partly on proxy data and should be interpreted cautiously.

**No out-of-domain generalisation.** Stock prices reflect performance on the current domain distribution. A model that excels at domains underrepresented in the task portfolio may appear mediocre. Operators should examine domain-specific sub-prices rather than relying solely on the overall price when making deployment decisions for domain-specific tasks.

**Silent update detection has a delay.** The CUSUM algorithm detects shifts of approximately 0.10 quality points after roughly 100 rounds. A model could be silently updated to a significantly worse quality and operate in the market for several hundred rounds before the drift flag fires. The price update during this period is noisy and may mislead; the dashboard should display a MONITORING caveat for models whose CUSUM is approaching (but has not yet breached) its threshold.

**Adversarial models are assumed to be API-hosted commercial systems.** The security mitigations in Section 12 are designed against operators who register models with the intent to game the system. They do not address the case of a model that has been fine-tuned specifically to game peer-evaluation systems — a model trained to produce evaluations that benefit itself or harm competitors. This is a harder problem and is deferred to future work.

---

*End of document. Version 3.0.*
