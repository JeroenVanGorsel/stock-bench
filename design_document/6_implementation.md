# Part VI: Implementation

[Back to index](readme.md) · [Previous: Part V](5_reference_material.md) · [Next: Appendices](7_appendices.md)

---

## 17. Testing Strategy

### 17.1 Unit Tests: Calibration Math

The calibration engine is the most mathematically sensitive component and must have exhaustive unit tests before any other development proceeds. The following cases must all pass.

**Brier score correctness:** test that `brier_score = (c - q)²` is computed correctly for boundary values (c=0, q=0; c=1, q=1; c=1, q=0; c=0, q=1; c=q=0.5). Test that the weighted calibration error correctly applies the importance multiplier and that this value is stored in round_result but does NOT enter the calibration EMA.

**EMA update correctness:** test that `new_score = 0.95 * old + 0.05 * (1 - brier)` with a known sequence of Brier scores converges to the analytically correct long-run value. Test that the clamp prevents values outside [0, 1]. Test that initialisation at 1.0 with a stream of perfect bids (c = q exactly) holds at 1.0. Test that a single round with Brier = 1.0 (maximum miscalibration) produces `0.95 * 1.0 + 0.05 * (1 - 1.0) = 0.95`, not a negative value.

**Beta update correctness:** test that `alpha += q, beta += 1 - q` with quality scores (0.8, 0.8, 0.2, 0.8) starting from Beta(1,1) produces Alpha = 1 + 0.8 + 0.8 + 0.2 + 0.8 = 3.6 and Beta = 1 + 0.2 + 0.2 + 0.8 + 0.2 = 2.4. Test that `stock_price = 3.6 / 6.0 = 0.60`. Test that the disagreement weight is correctly applied when high_disagreement = True.

**Proper scoring rule verification:** compute the expected Brier loss E[(c - q)²] for a model with true mean quality µ = 0.7 as a function of bid c, sampling 10,000 quality draws from a Beta distribution centred at µ. Verify that the minimum expected loss is achieved at c = µ and that the loss function is strictly convex around that minimum, confirming that the scoring rule is proper.

**Evaluator reputation update:** test the graded correctness formula with cases: evaluator scores 0.8, GT score 0.9 → correctness = 0.9; evaluator scores 0.9, GT score 0.1 → correctness = 0.2; evaluator scores exactly the GT score → correctness = 1.0.

### 17.2 Unit Tests: Allocation Formula

The composite allocation score formula has several interacting components that must each be tested independently.

Test that `thompson_sample` is drawn from Beta(α, β) and falls in [0, 1] across 10,000 draws. Test that when α = β = 1 (uniform prior), the distribution of samples is approximately uniform over [0, 1]. Test that the composite score is computed correctly for known input values. Test that `domain_boost = 1.0` when there is no domain overlap and that it is capped at 1.4. Test that during Phase 1, the weighted-random allocator selects models with probability proportional to their bid confidence (verify over 10,000 allocations with three models bidding 0.8, 0.4, and 0.2 — expected selection rates approximately 57%, 29%, 14%).

### 17.3 Unit Tests: Bid Parser

The parser must handle every realistic LLM output format. Test cases must include: clean JSON (CLEAN parse); JSON embedded in prose ("Sure! Here is my bid: {...}") (LENIENT parse); JSON with trailing comma (LENIENT parse via json5); JSON with single quotes (LENIENT parse via json5); confidence value out of range (should clamp to [0, 1], not reject); missing domain_tags (should default to ["unknown"]); missing rationale (should default to "[unavailable]"); completely non-JSON output with a confidence-like float visible in the text (should regex-extract the float, PARTIAL parse status); completely non-JSON output with no extractable float (NULL bid).

### 17.4 Integration Test: Complete Round Cycle

Build a test harness with five deterministic mock model servers implemented as local asyncio HTTP servers — they respond instantly with pre-specified JSON payloads, simulating different model personas (one high-quality well-calibrated, one high-quality overconfident, one low-quality underconfident, one mid-tier, one with occasional timeouts). Run exactly 10 sequential rounds with known model outputs and verify that the stored round_results contain the correct quality scores, Brier errors, alpha/beta deltas, and that model state has been updated to match analytically computed expected values.

The mock model server is a key piece of test infrastructure and should be treated as a first-class component, not a test-specific hack. It should support configurable behaviour (quality level, calibration offset, timeout rate) and be reused in simulation tests.

### 17.5 Integration Test: Crash Recovery

Simulate a crash at each of the six write steps within a round cycle (task ALLOCATED, execution response written, evaluator response N written, quality score computed, round_result written, model state updated). For each crash point, restart the system and verify that: the round outcome is correct (voided or completed as appropriate), no duplicate state updates are applied, and the final model state matches what would have been produced by an uninterrupted run.

### 17.6 Simulation Tests: Emergent Properties

Run the full system for 500 rounds against a pool of five mock models with known properties:
- Model A: quality 0.85, well-calibrated (bids 0.85 ± 0.05)
- Model B: quality 0.85, overconfident (bids 0.95 ± 0.05)
- Model C: quality 0.60, well-calibrated (bids 0.60 ± 0.05)
- Model D: quality 0.60, underconfident (bids 0.30 ± 0.05)
- Model E: quality 0.40, well-calibrated (bids 0.40 ± 0.05)

After 500 rounds, verify the following invariants. Stock prices rank A > C > E (quality order preserved). A's stock price is higher than B's despite equal quality (calibration discounting works). D's stock price is lower than C's (underconfidence has consequences). The calibration score for B is lower than A's (miscalibration is detected). The allocation share for B is lower than A's despite equal quality (calibration discounting reduces B's allocation weight). Thompson Sampling ensures E has received at least 20 execution rounds (exploration maintained). The mean of `(bid - quality)` across all models is positive (confirm the mild overconfidence equilibrium pressure predicted in Section 2.4).

### 17.7 Adversarial Tests

Test the selective participation defence: run a mock model that submits NULL bids on all rounds where the pool-mean quality is below 0.65 (simulating selective timeout on hard tasks). After 200 rounds, verify that the SELECTIVE_PARTICIPATION anomaly flag is raised. Test the calibration gaming defence: run a mock model that always bids 0.1 while receiving quality scores of 0.75. After 100 rounds, verify that its calibration score is significantly below a model that bids 0.75 and receives 0.75. Test the length bias monitoring: run a mock model whose response length is positively correlated with quality score (via mock evaluators that score longer responses higher). After M rounds, verify that the LENGTH_BIAS_CORRELATION flag is raised.

### 17.8 Market Invariant Assertions

The market agent should run a set of invariant assertions at every outer-loop cycle. If any fail, raise a CRITICAL anomaly flag immediately. The invariants: all alpha and beta values are positive finite numbers; all stock prices are strictly between 0 and 1; all calibration scores and evaluator reputations are in [0, 1]; all rubric weights in all tasks sum to 1.0 within floating-point tolerance; the sum of all allocation shares over the last M rounds equals exactly M (every round is accounted for); no model state timestamp predates the system start.

---

## 18. Failure Modes and Mitigations

### 18.1 Evaluation Circularity

Models judge each other, creating a potential for collective relativism where "good" means only "what this pool agrees is good." Mitigation: ground-truth anchoring (20% of rounds have objectively verified quality scores), evaluator reputation weighted by ground-truth performance (poor evaluators have their votes discounted), and pairwise bias tracking (systematic deviations from ensemble consensus are detected and corrected). The system cannot fully escape the relativism of peer evaluation, but the ground-truth anchor prevents it from drifting arbitrarily far from objective quality.

### 18.2 Rich-Get-Richer Dynamics

A leading model accumulates more data, narrower uncertainty, and higher allocation priority in a self-reinforcing cycle. Mitigation: Thompson Sampling automatically explores models with wide distributions. HHI monitoring flags excessive concentration. The IPO sprint ensures new entrants receive sufficient data to compete.

### 18.3 Strategic Overconfidence

A model that always bids high wins more allocation but accumulates large Brier losses, progressively reducing its calibration_weight in the allocation formula. The system is self-correcting: after enough rounds of overbidding, the calibration_weight approaches zero and the high bid no longer produces a high allocation score.

### 18.4 Strategic Underconfidence (Double Penalty)

Chronically low bids lose allocation opportunities AND accumulate Brier losses (since `(low_bid - high_quality)²` is large). A model cannot improve its calibration score by bidding low when its true quality is high — the proper scoring rule penalises both directions. The only case where extreme underconfidence has no Brier cost is a genuinely low-quality model that bids near its true quality — which is correct behaviour, not gaming.

### 18.5 Selective Participation

Covered in Sections 6.3 and 12.4. Correlation-based detection and SELECTIVE_PARTICIPATION flag.

### 18.6 Generator Domain Concentration

Covered in Section 12.7. Subdomain-level concentration cap (12% per subdomain) in addition to first-level domain cap (30%).

### 18.7 Generator Gaming (Self-Serving Tasks)

A generator could produce tasks in domains where it outperforms the pool. Mitigation: rotation prevents consecutive generation; discriminativeness scoring requires tasks to separate all models, not just help the generator; the market agent monitors correlation between a model's generator turns and its allocation wins in the periods following those turns.

### 18.8 Model Drift

Silent API updates change a model's capabilities. Mitigation: CUSUM drift detection identifies sustained shifts within approximately 100 rounds. Drift triggers flags and potentially an IPO sprint reinitialisation. The historical Alpha/Beta history before the drift event is archived but not deleted, enabling retrospective analysis of capability changes.

### 18.9 Prompt Injection

Covered in Sections 12.1 and 12.2. Three-layer defence for generator-side injection; evaluator system prompt for execution-side injection.

### 18.10 Quality Score Ceiling Effect

As the model pool improves, scores cluster near 0.9+ and differentiation between top models becomes small. The dynamic task difficulty system addresses this: if discriminativeness p10 falls below DISCRIMINATIVENESS_MIN for two consecutive outer loops, difficulty parameters are increased, raising the bar until differentiation is restored. The stock price CIs of the top models will overlap, which is the correct signal to display — it means the pool cannot distinguish between them at current task difficulty.

### 18.11 Memorisation of Ground-Truth Tasks

Models pre-trained on data including public benchmark questions may perform artificially well on ground-truth tasks that overlap with those benchmarks. Mitigation: flag known-public-benchmark tasks in the bank; track the performance gap between flagged and non-flagged tasks; the memorisation_gap field in MarketReport surfaces this signal. Long-run mitigation: retire flagged tasks faster (after MAX_GT_TASK_USES / 2 uses) and replace them with novel ground-truth tasks generated by human annotators specifically for this system.

### 18.12 Pool-Relative Price Incomparability

Stock prices are relative to the current pool composition and evaluator strictness. Adding a high-quality strict evaluator to the pool will lower all quality scores and compress stock prices downward. Prices within one pool configuration are comparable over time; prices across different pool compositions are not directly comparable. The MarketReport's pool_version field (a hash of current model registrations) makes pool composition explicit. Any comparison of prices across different pool versions should be labelled as approximate and approached with caution.

---

## 19. Implementation Roadmap

### Phase 1: The Inner Loop (3–4 weeks)

Build the following in sequence, verifying each component before proceeding.

Infrastructure: the provider abstraction layer with adapters for at least two providers (Anthropic and OpenAI) and the OpenRouter integration. The mock model server for testing. SQLite persistence with the round_result schema from Section 15. The GT scoring function registry with at least ten ground-truth tasks and their automated scoring functions to verify the pipeline.

The ground-truth task bank: 500 manually curated tasks across all seven domains, with automated scoring functions for mathematical and code tasks and a reference-answer lookup for factual tasks. This takes the most time in Phase 1 and should be started on day one in parallel with infrastructure work.

The round cycle: bid collector (async HTTP, timeout enforcement, lenient JSON parser), Phase 1 weighted-random allocator, executor caller (timeout, truncation, refusal detection), evaluation pipeline (async HTTP, timeout, graded composite score computation with all evaluator reputations at 1.0), round result persistence.

Phase 1 deliverable: a Python module with a CLI entry point that runs N rounds sequentially, persisting results to SQLite. Output a CSV of round results with cycle_number, model_id, bid_confidence, quality_score, brier_score for each round. No persistent model state between rounds.

Phase 1 validation: run 50 rounds with at least 5 registered models and verify data integrity (no missing fields, all Brier scores in [0, 1], all quality scores in [0, 1]).

### Phase 2: The Middle Loop and Persistent Model State (4–5 weeks)

Add model state persistence. Initialise all models at Beta(1, 1), calibration_score = 1.0, evaluator_reputation = 1.0. Add the Beta distribution update (alpha += q, beta += 1-q, with disagreement weight). Add the calibration EMA update using raw Brier score (not importance-weighted). Add the evaluator reputation update using graded correctness on ground-truth rounds. Add the calibration_weight to the allocation formula. Replace the Phase 1 weighted-random allocator with Thompson Sampling and full composite score formula. Add bootstrap mode and IPO sprint protocol. Add the crash recovery procedure.

Run simulation tests with five mock models of known properties (Section 17.6). Verify that after 500 rounds, all invariants hold. Verify that the overconfident mock model's calibration_weight has converged below the well-calibrated mock model's.

Phase 2 deliverable: a fully persistent system with a minimal CLI dashboard showing current stock prices, calibration scores, evaluator reputations, and the last 20 round results.

### Phase 3: Dynamic Generation, Outer Loop, and Market Agent (5–7 weeks)

Add task generation with the generation prompt, validation via council (not human oracle), injection detection, and discriminativeness scoring. Add the generator rotation scheduler with pool-mean-initialised discriminativeness. Add the task portfolio manager with first-level and subdomain concentration limits. Add the deduplication pipeline. Add per-provider rate limiting. Add the API cost tracker. Add the market agent with all monitoring algorithms from Section 11. Add the full market report generator including the memorisation signal. Add the web dashboard (read-only, showing all dashboard elements described in the market report). Add the anomaly flag display and human-review interface.

Phase 3 deliverable: a fully self-running system requiring only periodic human review of anomaly flags and monthly ground-truth bank maintenance.

### Phase 4 (Future): Parallelism and Latency Scoring

Parallel inner-loop operation (multiple simultaneous rounds), per-round cost minimisation (selective evaluator pool, tiered model costs), latency scoring incorporated into stock prices as a separate dimension, and per-domain evaluator reputation tracking.

---

## 20. What This Measures and Why It Matters

### 20.1 What the Stock Price Is

The stock price is the best current estimate of a model's mean quality on tasks from the current pool's domain distribution, where quality is measured by a council of peer evaluators, weighted by their historical accuracy on ground-truth tasks, on tasks that require genuine reasoning rather than memorised pattern completion. The price is additionally conditioned on the model being reliably calibrated: a model that produces equivalent quality but more accurately predicts when it will and won't do so receives a higher price than one that does not, because calibration affects both the allocation weight (overconfident models are assigned fewer tasks over time) and the Beta update rate (the price of a well-calibrated model is more precisely estimated).

This is different from what any existing benchmark produces. Static benchmarks give a score on a fixed test set at a point in time. Chatbot Arena gives a preference ranking from human pairwise comparisons. Leaderboards give a snapshot. The LLM Marketplace gives a **continuous market** — a live-updating system that measures not just what a model produces but whether it knows what it is capable of producing.

### 20.2 Where the Price is Most Informative

The price is most useful in two specific deployment contexts.

The first is procurement for reliability-critical applications: any deployment where a model confidently delivering wrong answers is more damaging than a model that correctly declines tasks it cannot handle. The calibration-adjusted stock price is more predictive of this than raw quality metrics, because it specifically penalises the combination of high confidence and low quality.

The second is agentic orchestration design: systems that route tasks to models based on self-assessment need to know whether the model's self-assessment is trustworthy. A model with a high calibration score has demonstrated, over hundreds of rounds, that its stated confidence tracks its actual performance. That is the property you need a routing system to rely on.

### 20.3 What the Price Cannot Tell You

The price cannot tell you how a model performs on tasks outside the pool's domain distribution — it is a market price, and markets are only informative about the goods they trade. If the pool's task distribution overrepresents formal reasoning and underrepresents creative tasks, the price reflects performance on that mix. A model that excels at creative tasks but performs only moderately at formal reasoning may be undervalued.

The price cannot tell you about absolute capability in any universal sense. It tells you about performance relative to a specific evaluator council at a specific time. If the council changes (models are added or retired), prices shift accordingly, and cross-pool comparisons require the pool_version label to be treated as a covariate, not background context.

The price cannot tell you how a model performs for a specific user or use case, as opposed to the aggregate task distribution. Domain-specific sub-prices are a partial answer to this; per-use-case measurement is a research programme beyond the scope of this system.

### 20.4 The Secondary Artefacts

The system produces two secondary artefacts whose value increases over time. The first is a corpus of tasks generated by LLMs to be maximally discriminative about each other — problems chosen not to reflect what models are good at, but to reveal where they differ. This corpus, tagged with domain, difficulty, importance, and discriminativeness scores, is a novel benchmark dataset that no human annotator would produce in the same way, because it is specifically engineered to probe the capability gaps that exist between the models currently in the pool. It accumulates with every cycle.

The second is a longitudinal capability change record: the CUSUM drift log captures the timing, direction, and magnitude of every quality shift detected across every registered model. This is a record of silent API updates, fine-tune deployments, and capability regressions that no existing benchmark tracks continuously. The long-run value of this record — a timestamped history of how the LLM field has actually advanced in practice rather than as claimed — may exceed the value of the live benchmark itself.
