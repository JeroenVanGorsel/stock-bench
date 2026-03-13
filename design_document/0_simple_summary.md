# Simple Summary

[Back to index](readme.md)

## What this project is

This project is building an **LLM benchmark system** where **LLMs benchmark one another**.

Instead of giving models a static test once and publishing a leaderboard, this system runs like a small market:

1. a task is chosen,
2. multiple models say how confident they are,
3. one model is picked to do the task,
4. the other models score the answer,
5. the system updates each model's running score and calibration record,
6. the results are stored and shown on a dashboard.

## Why it is different

Most benchmarks are fixed exams. They show how a model did on a frozen set of questions.

This project is different because it is **continuous**:

- models keep competing over time,
- models judge each other,
- the system tracks whether a model is **actually good** and whether it **knows when it is likely to do well or badly**.

That second part matters a lot. A model that is good but wildly overconfident can be risky. A model that is slightly weaker but honest about its limits can be more useful in real systems.

## The main idea in simple terms

You can think of each model as having two important traits:

- **quality** — how strong its answers are
- **calibration** — how accurately it predicts its own quality before answering

The system measures both.

Each model gets a market-style score, sometimes described like a stock price. That score is a compact way to represent how strong the model looks based on repeated rounds of evidence.

## How one round works

A single round looks like this:

### 1. Pick a task
A task can come from a curated bank or be generated dynamically.

### 2. Ask models to bid
Each model gives a confidence estimate for how well it thinks it will do.

### 3. Allocate one executor
The system chooses one model to actually answer the task. The choice depends on prior performance, exploration, and the current bid.

### 4. Collect the answer
That selected model produces the response.

### 5. Have the council evaluate it
The remaining models score the answer across dimensions like accuracy, usefulness, and clarity.

### 6. Update market state
The system updates:

- the model's running quality estimate,
- its calibration score,
- evaluator reputation,
- logs and reports for later analysis.

## What the system is trying to learn

Over many rounds, the project tries to answer questions like:

- Which models consistently produce high-quality results?
- Which models are honest about their own strengths and weaknesses?
- Which models are good evaluators of other models?
- Which models improve or drift over time?
- What kinds of tasks separate strong models from weak ones?

## Why the market framing helps

The market format creates pressure for better self-reporting.

If a model always claims it will do amazingly well, but then performs badly, the system penalizes that mismatch. If a model gives realistic bids, its calibration looks better over time.

So the system is not only measuring answers. It is also measuring **self-knowledge**.

## What is in scope

At a high level, this design covers:

- a Python backend,
- task storage and round logs,
- provider adapters for multiple LLM APIs,
- bidding, allocation, execution, and evaluation,
- persistent scoring over time,
- anomaly detection and drift monitoring,
- a read-only dashboard.

## Important caveat

The model scores are **pool-relative**.

That means a model's score depends on which other models are in the benchmark and how strict those evaluator models are. So the score is most useful:

- for comparing models inside the same pool,
- for watching changes over time inside the same setup.

It is less useful as a universal absolute number.

## In one sentence

This project is a continuously running benchmark where LLMs bid, execute, and judge one another so the system can measure both **answer quality** and **how well each model understands its own ability**.
