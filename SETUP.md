# Stock Bench Setup

This guide explains the minimum steps needed to run the project locally and then move on to live model tests.

## 1. What you need

- Windows PowerShell or another shell
- Python 3.11+
- API credit and access for at least one provider
- At least 4 models configured in the pool

For the current example configuration in [models.json.example](models.json.example), the only required provider credential is an OpenRouter API key.

## 2. Create a virtual environment

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this once in PowerShell first:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 3. Install the project

Install the package and development dependencies:

```powershell
pip install -e .[dev]
```

## 4. Create the environment file

Copy [.env.example](.env.example) to `.env`.

```powershell
Copy-Item .env.example .env
```

Then edit `.env`.

### Minimum `.env` for the default model list

```dotenv
OPENROUTER_API_KEY=your_key_here
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
STOCK_BENCH_DATABASE=stock_bench.db
STOCK_BENCH_BOOTSTRAP_ROUNDS=8
STOCK_BENCH_MIN_EVALUATORS=3
STOCK_BENCH_ANCHOR_RATIO=0.2
STOCK_BENCH_REQUEST_TIMEOUT=60
```

## 5. Create the active model registry

Copy [models.json.example](models.json.example) to `models.json`:

```powershell
Copy-Item models.json.example models.json
```

Then edit `models.json` if needed.

### Important rules

- Keep at least **4 active models** in the pool.
- Make sure the model IDs are real and available to your account.
- If you keep the example file unchanged, all models go through OpenRouter.
- If you change a model to `provider = "openai"` or `provider = "anthropic"`, set the matching API key in `.env`.

## 6. Seed the local database

This creates the initial model state and seed tasks.

```powershell
python -m stock_bench.cli seed
```

This should create the SQLite database configured by `STOCK_BENCH_DATABASE`.

## 7. Start the dashboard

Run the local web app:

```powershell
python -m stock_bench.cli serve
```

Then open:

- http://127.0.0.1:8000

## 8. Run benchmark rounds

### Run a single round

```powershell
python -m stock_bench.cli run-round
```

### Run a short batch

```powershell
python -m stock_bench.cli run-batch --count 3
```

You can also trigger rounds from the dashboard buttons.

## 9. Run tests

```powershell
python -m pytest
```

## 10. Recommended first live test

Before doing larger runs:

1. confirm `.env` has a valid `OPENROUTER_API_KEY`
2. confirm `models.json` contains only models your account can access
3. run `python -m stock_bench.cli seed`
4. run `python -m stock_bench.cli run-round`
5. open the dashboard and confirm the round appears

## 11. Common failure points

### `OPENROUTER_API_KEY is not configured`

Your `.env` file is missing the key or was not created.

### `At least four active models are required`

Your `models.json` has fewer than 4 enabled entries.

### provider/model access errors

The configured model ID may not be available to your account, or the account may not have credit.

### not enough evaluator responses

One or more provider calls timed out or failed, leaving fewer than the configured minimum evaluator responses.

## 12. Current MVP limitations

- prices are provisional during bootstrap
- prices are pool-relative, not globally comparable
- ground-truth coverage is intentionally small
- generated-task validation is still lightweight
- live rounds can incur real API cost