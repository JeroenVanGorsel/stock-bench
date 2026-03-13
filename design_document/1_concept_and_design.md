# LLM Marketplace: Technical Design Document

**Version 3.0 — March 2026**

[Back to index](readme.md) · [Next: Part II](2_inner_loop.md)

---
 Part I establishes concepts. Parts II and III describe the inner, middle, and outer loops. Part IV covers operations and security. Part V contains reference material (data models, prompt templates). Part VI covers implementation. Appendices contain configuration parameters (moved from inline to reference), a glossary, and a known limitations inventory. Readers building the codebase should work through Parts I–III in order, then use Parts IV–VI as reference.

---

# Part I: Concept and Design

---

## 1. What This Is

The LLM Marketplace is a self-running benchmarking system in which a pool of language models continuously evaluates itself. Models bid on incoming tasks by asserting their own capability, one model executes each task, a council of the others judges the result, and the discrepancy between what a model claimed and what it actually delivered generates a persistent economic signal — its stock price. The benchmark is not something run against the system. The system running is the benchmark.

This differs from existing LLM evaluation in a precise way. Static benchmarks (MMLU, HumanEval, BIG-Bench) measure a model at a moment in time against a fixed test set. Chatbot Arena collects human preferences through blind pairwise comparison. RouteLLM and Not Diamond route tasks based on an external router's prediction. All treat models as objects to be measured by something external. The LLM Marketplace treats models as agents whose value is discovered through competitive interaction, under conditions where honest self-reporting is mathematically incentivised.

A critical qualification belongs here, not in a footnote: the incentive structure created by the proper scoring rule (Section 2.1) assumes models behave as rational agents optimising for Brier loss. LLMs are not. They produce outputs based on training distributions, not online loss minimisation. The system does not make models honest by decree — it makes honest reporting *representationally natural* in the sense that a model trained to be accurate and calibrated will naturally produce outputs that look like honest bids. Whether any given model's bids are genuinely calibrated or merely formatted correctly is an empirical question the system is designed to answer. The scoring rule creates the right measurement context; it does not guarantee what will be found there.

Two scope decisions. The minimum pool size is four models: below four, the evaluator council has fewer than three members, which is statistically inadequate and creates trivial collusion opportunities. The system operates as continuous research infrastructure — the dashboard is read-only, models are registered by operators, and there is no end-user interaction.

One interpretive constraint that must be stated clearly: stock prices are **pool-relative**. When this document says "a price of 0.80 means a model delivers roughly 0.80 quality," this is shorthand that glosses over the fact that quality scores are issued by the council, whose composition and strictness vary. A pool with stricter evaluators will produce lower quality scores for the same execution quality. Prices are comparable across time for the same pool configuration, and across models within the same pool at the same time. They are not directly comparable across pools of different composition. Every published price should be labelled with the pool version and composition snapshot that produced it.

---

## 2. Foundational Concepts

### 2.1 The Proper Scoring Rule

A proper scoring rule is a loss function structured so that reporting your true belief minimises your expected loss. The Brier score — the squared error between a stated probability and the eventual outcome — is the canonical example for binary outcomes. If you genuinely believe you have a 70% chance of success, reporting 0.7 minimises your expected Brier loss. Reporting 0.9 when your true belief is 0.7 increases expected loss: the occasions where you succeed see modest improvement (0.01 instead of 0.09) but the occasions where you fail see large worsening (0.81 instead of 0.49), and the expectation over all cases penalises the overstatement.

In this system, quality scores q are continuous values in [0, 1], not binary outcomes. The Brier score extends to continuous targets: for confidence bid c and received quality q, the calibration error is (c - q)², and this remains strictly proper as long as the model is asked to estimate its *expected* quality score. The proof is identical: the expected value of (c - q)² over the distribution of possible q values is minimised when c equals E[q | task, model]. For any other c, the expected loss is higher. The code comment wherever this formula appears should read: "This is the Brier score for continuous outcomes. The optimal bid under quadratic loss is the conditional expected quality score, not a probability of success."

What this incentive structure does and does not provide: it makes truthful self-assessment the payoff-maximising strategy *if the model is optimising for the loss function*. It does not guarantee that any specific LLM actually produces optimal bids. A model that consistently overbids does so at a cumulative cost to its calibration score and therefore its allocation weight — this is how the incentive operates in practice, as an accumulating penalty, not as a logical guarantee of honesty.

### 2.2 Thompson Sampling and the Exploration-Exploitation Trade-off

Thompson Sampling solves the multi-armed bandit problem: given N models with unknown quality distributions, how do you allocate tasks to maximise total quality while still learning about all models? The greedy strategy — always pick the current best estimate — creates the rich-get-richer dynamic described in Section 18.2. Uniform exploration is wasteful once priors have accumulated. Thompson Sampling splits the difference: maintain a probability distribution over each model's true quality, and at each allocation step, sample one value from each model's distribution and pick the highest sample.

Models with wide distributions (few observations) occasionally sample very high and win rounds they would never win under a greedy strategy, ensuring the system never permanently abandons exploring a model. As observations accumulate, distributions narrow, allocation converges toward genuinely better models, but never fully abandons weaker ones.

Thompson Sampling assumes stationary reward distributions. API-hosted models are silently updated by their providers, violating this assumption. This violation is not a reason to abandon Thompson Sampling but a reason to supplement it with drift detection (Section 11.3), which identifies when a model's quality distribution has shifted and reinitialises its prior.

### 2.3 The Beta Distribution as Market Price

Each model's quality is modelled as Beta(α, β), where α accumulates evidence of good performance and β accumulates evidence of poor performance. Three reasons for this choice: the Beta distribution is bounded to [0, 1], matching the range of quality scores (a Gaussian can produce nonsensical negative or above-unity quality estimates); it is conjugate to the Bernoulli likelihood, making updates analytically tractable; and its parameters have direct interpretation — α / (α + β) is the mean quality estimate, and α + β is the total evidence weight.

The update rule uses continuous quality scores rather than binary wins and losses:

```python
# After a round where the executor receives quality score q
alpha += q          # Full credit for quality
beta  += (1.0 - q)  # Full credit for quality shortfall
```

This is the correct update. Version 2.0 used `alpha += q * cs` where cs is the calibration score. That was a conceptual error: the Beta distribution should track *actual execution quality as measured by the council*, not quality adjusted by how well the model predicted that quality. The council's measurement is valid regardless of whether the model was well-calibrated. Penalising the Beta update for miscalibration would mean a miscalibrated-but-capable model has its stock price suppressed toward 0.5, which is wrong — we know its quality from the council's scores; we just also know its self-assessment is unreliable. These two signals should remain separate. The calibration score affects the allocation formula only, not the quality estimate.

At initialisation, all models start at Beta(1, 1), the uniform prior. The stock price is α / (α + β). The volatility is the Beta standard deviation: `sqrt((α × β) / ((α + β)² × (α + β + 1)))`. A model with price 0.82 and volatility 0.03 is reliably good. A model with price 0.82 and volatility 0.12 is inconsistent and correspondingly less valuable as an allocation target.

One long-run property to understand: as a model accumulates many rounds with calibration score near 1.0, the Beta parameters grow roughly as α ≈ q̄ × N and β ≈ (1 - q̄) × N. After 1,000 rounds at mean quality 0.80, α ≈ 800, β ≈ 200, and volatility ≈ 0.013. The price becomes highly stable and barely moves. This is the correct behaviour — you have strong evidence — but it means genuine capability changes after this point take many rounds to register. Drift detection (Section 11.3) is the countermeasure: it detects sustained quality shifts and triggers a partial prior reinitialisation.

### 2.4 Calibration as a First-Class Capability

Standard benchmarks measure outputs. This system also measures whether a model knows what it is capable of producing. A highly capable but overconfident model presents wrong answers with high confidence — a serious deployment liability. A moderately capable but well-calibrated model accurately flags its own uncertainty, which allows downstream systems to route tasks appropriately and display uncertainty honestly. The marketplace makes this distinction economically legible by making calibration errors affect allocation priority.

One important asymmetry in how calibration penalties interact with allocation deserves explicit acknowledgment. An overconfident model bids high, wins more allocation rounds than its quality deserves, but accumulates Brier losses that reduce its calibration weight, progressively discounting its bids. An underconfident model bids low, loses allocation rounds, and *also* accumulates Brier losses (since `(0.2 - 0.8)² = 0.36` is a large error). Underconfidence incurs a double penalty: lost allocation opportunities *and* calibration damage. This asymmetry means the equilibrium bid may trend slightly above true expected quality across the pool. Phase 2 analysis should monitor the pool-wide mean of `(bid - quality)` to check whether this bias manifests empirically and whether the weight parameters need adjustment.

---

## 3. System Architecture

### 3.1 The Three Loops

The system runs as three nested loops of different cadences.

The **inner loop** is a single task cycle: select a task, broadcast bid requests, allocate to one model, execute, evaluate by council, record results, update Beta distributions. This runs continuously. Its practical cadence is bounded by API latency — roughly one round every 25–45 seconds under normal conditions. The inner loop is the only loop with real-time data dependencies; it should never wait on the middle or outer loop.

The **middle loop** is calibration accounting. It runs as a background job every K = 50 completed inner-loop cycles. It reads the last K round results, recomputes each model's rolling calibration EMA and evaluator reputation EMA, and writes updated scores back to model state. The inner loop reads the latest calibration scores from model state on each round; it does not wait for the middle loop to complete before proceeding.

The **outer loop** is market monitoring. It runs as a background job every M = 200 completed inner-loop cycles. It computes market-wide statistics, runs drift detection, checks pairwise evaluator bias, assesses task discriminativeness trends, and generates a market report. It does not modify model state directly — it creates anomaly flags and recommendations. The only automatic interventions are task-generator suspension for detected prompt injection and IPO sprint reinitialisation for models with severe detected drift.

### 3.2 Data Flow

The inner loop reads from model state (Beta parameters, calibration scores) and writes round results to the round log. The middle loop reads from the round log and writes updated calibration and reputation scores back to model state. The outer loop reads from both model state and the round log. The key invariant: **no loop blocks on any later loop**. Middle and outer loops run asynchronously, reading committed data and writing summary updates.

### 3.3 Concurrency Within the Inner Loop

Steps within a single inner-loop cycle run in this order:

**Bid collection** is concurrent: all registered ACTIVE models receive bid prompts simultaneously via async HTTP calls. Per-model bid timeout: BID_TIMEOUT_SECONDS = 15. Models that exceed this are excluded from the bid pool for this round; their timeout is logged with reason code TIMEOUT. A minimum of two bids is required to proceed. If fewer than two are received, the round is voided and the task re-queued.

**Allocation** is synchronous: one model is selected from the received bids using the composite allocation score formula (Section 7.1).

**Execution** is synchronous: the selected model is called with a timeout of EXECUTION_TIMEOUT_SECONDS = 60. If execution times out, the round is voided and the task re-queued. The voided round is logged but no model state is updated.

**Evaluation** is concurrent: all models except the executor receive evaluation prompts simultaneously. Models that timed out during bidding are *included* in the evaluation pool — bid availability and evaluation availability are independent. Per-evaluator timeout: EVALUATION_TIMEOUT_SECONDS = 15, with a two-second grace window to collect near-miss responses before finalising the quality score. A minimum of MIN_EVALUATORS_PER_ROUND = 3 evaluator responses is required. If fewer arrive, the round is voided.

**State update** is synchronous: Beta distributions are updated, then calibration EMA is updated. The ordering matters (Section 10.4).

### 3.4 Parallelism

The current design runs one task cycle at a time (sequential inner loop). This is the correct starting point: sequential operation is easier to debug and reason about, and a single round of N=10 models already involves ~21 concurrent API calls. Parallel cycle operation (running multiple rounds simultaneously with different subsets of models) is a Phase 4 optimisation that requires careful management of evaluation pool membership and model state write contention. It is deferred explicitly; this document does not design it.

### 3.5 Task Queue Flow Control

Dynamic task generation (Section 5.3) must not outrun task execution. If generation is faster than execution — which it typically is, since generating a task prompt costs one API call while executing and evaluating costs 2N calls — the task queue grows unboundedly. The flow control rule is: generation fires only when queue depth drops below QUEUE_MIN_DEPTH = 20 tasks. The generator is triggered to produce tasks in batches of QUEUE_BATCH_SIZE = 10 until the queue is above QUEUE_TARGET_DEPTH = 50. At normal execution speed (one round every 30 seconds), 50 tasks represents 25 minutes of buffer, which is ample to absorb generation latency.

### 3.6 State Diagram

A task moves through the following states: QUEUED → BID_OPEN → ALLOCATED → EXECUTING → EVALUATING → COMPLETE | VOIDED. Voided tasks return to QUEUED. All state transitions are persisted before being acted upon so that a restart can resume from the last committed state without loss.

---

## 4. Bootstrap and Cold Start

### 4.1 The Chicken-and-Egg Problem

At initialisation, no model has a history. Bid prompts cannot show meaningful performance context. All calibration scores are 1.0. All Beta distributions are Beta(1, 1). Publishing stock prices immediately would produce and surface meaningless numbers. The bootstrap protocol prevents this.

### 4.2 The Bootstrap Phase

During bootstrap, task allocation is **uniform random**: a model is selected from all registered ACTIVE models with equal probability, ignoring both Thompson Sampling and bid confidence. This prevents any model from benefiting from lucky early rounds before the prior accumulates evidence. Bootstrap mode is active until every registered model has completed its IPO sprint of IPO_SPRINT_ROUNDS = 30 rounds.

Stock prices are hidden from the dashboard during bootstrap. The dashboard shows each model as "calibrating" with a progress indicator (rounds_completed / IPO_SPRINT_ROUNDS).

The initial task bank consists entirely of curated ground-truth tasks. Dynamic generation is disabled during bootstrap and enabled only after each individual model has completed its IPO sprint — not after the entire pool has, because waiting for the last model to finish unnecessarily delays generation. The condition is: a model becomes eligible to generate tasks after it has completed its own IPO sprint.

### 4.3 Cold-Start Bid Prompts

During bootstrap rounds, the bid prompt cannot reference performance history that doesn't exist. The **bootstrap bid prompt** replaces the performance context block with: "You have no performance history in this system yet. Estimate your expected quality score for this task based on your general capabilities and the nature of the task described." The allocation mechanism ignores the confidence value during bootstrap (uniform random selection), so the bid is purely diagnostic — it starts building the rationale corpus without affecting allocation.

This requires two variants of the bid prompt: one for bootstrap rounds (no performance context), and one for production rounds (full performance context). Both share the same system prompt.

### 4.4 New Models Joining a Running System

When a new model is registered after the system is already running, it enters an IPO sprint of 30 forced-allocation rounds. During the sprint, the new model is allocated a task roughly 1 in every 6 rounds, regardless of its allocation score. The 1-in-6 rate is fixed regardless of how many models are simultaneously in sprint: if three models are sprinting at once, each gets 1/6 of rounds, consuming half the round schedule for sprint tasks. This is preferable to the 1-in-4 rate from v2, which consumed 3/4 of rounds when three models were simultaneously sprinting.

During the new model's IPO sprint, its evaluations of other models are accepted and weighted by its evaluator reputation (initialised to 1.0, which reduces to the simple mean of evaluator scores — the correct neutral prior). The new model's evaluator reputation begins updating from its first ground-truth evaluation round.
