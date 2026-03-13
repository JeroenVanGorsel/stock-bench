const modelsBody = document.getElementById("models-body");
const roundsList = document.getElementById("rounds-list");
const warning = document.getElementById("warning");

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatMaybeNumber(value, digits = 3) {
  return typeof value === "number" ? value.toFixed(digits) : "n/a";
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

function renderModels(models) {
  modelsBody.innerHTML = "";
  for (const model of models) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td class="tooltip-anchor" data-tooltip="Internal model id: ${escapeHtml(model.model_id)}. Provider: ${escapeHtml(model.provider)}.">${escapeHtml(model.display_name)}</td>
      <td class="tooltip-anchor" data-tooltip="Pool-relative quality estimate. It updates after this model executes a round and gets scored by the council.">${model.stock_price.toFixed(3)}</td>
      <td class="tooltip-anchor" data-tooltip="Estimate uncertainty. This usually drops as the model completes more rounds.">${model.volatility.toFixed(3)}</td>
      <td class="tooltip-anchor" data-tooltip="Self-knowledge score. High calibration means the model's confidence bids have been close to the quality it later delivered.">${model.calibration_score.toFixed(3)}</td>
      <td class="tooltip-anchor" data-tooltip="Times this model has been selected as the executor.">${model.tasks_executed}</td>
    `;
    modelsBody.appendChild(row);
  }
}

function renderRounds(rounds) {
  roundsList.innerHTML = "";
  for (const round of rounds) {
    const fullPrompt = round.task.prompt;
    const item = document.createElement("div");
    item.className = "round-item";
    const prompt = fullPrompt.length > 180
      ? `${fullPrompt.slice(0, 180)}...`
      : fullPrompt;
    const confidence = typeof round.bid?.confidence === "number" ? round.bid.confidence.toFixed(3) : "n/a";
    const source = round.task?.source || "unknown";
    const outcome = round.execution_outcome || "unknown";
    const scoringBasis = typeof round.objective_score === "number"
      ? `objective anchor (${round.objective_score.toFixed(3)})`
      : "peer council";
    const provisional = round.provisional ? "yes" : "no";
    item.innerHTML = `
      <div class="round-head">
        <strong class="tooltip-anchor" data-tooltip="Cycle ${round.cycle_number} means the ${round.cycle_number}${round.cycle_number === 1 ? 'st' : ''} completed benchmark round stored in the database.">Cycle ${round.cycle_number}</strong>
        <span class="tooltip-anchor" data-tooltip="The executor is the model that won the bidding/allocation step and actually answered the task in this round.">${escapeHtml(round.executor_model_id)}</span>
      </div>
      <div class="subtle tooltip-anchor prompt-preview" data-tooltip="Full task prompt: ${escapeHtml(fullPrompt)}">${escapeHtml(prompt)}</div>
      <div class="round-meta">
        <span class="tooltip-anchor meta-chip" data-tooltip="Where this task came from. Seed and ground-truth tasks are curated anchors; dynamic_generation means a model created the task.">source ${escapeHtml(source)}</span>
        <span class="tooltip-anchor meta-chip" data-tooltip="The executor's bid before the round started. This is the model's self-estimate of the quality score it expected to receive.">bid ${confidence}</span>
        <span class="tooltip-anchor meta-chip" data-tooltip="Execution result returned by the executor call. COMPLETE means a normal response was recorded.">outcome ${escapeHtml(outcome)}</span>
        <span class="tooltip-anchor meta-chip" data-tooltip="Was this round still in bootstrap / provisional mode? Early rounds are noisier and should be interpreted more cautiously.">provisional ${provisional}</span>
      </div>
      <div class="metrics">
        <span class="tooltip-anchor metric-chip" data-tooltip="Final quality score used for the round. When there is no objective anchor, this is the council's weighted score for the executor response.">quality ${round.quality_score.toFixed(3)}</span>
        <span class="tooltip-anchor metric-chip" data-tooltip="Brier score = (bid - quality)^2. Lower is better. A value near 0 means the model predicted its own performance accurately.">brier ${round.brier_score.toFixed(3)}</span>
        <span class="tooltip-anchor metric-chip" data-tooltip="How many other models successfully scored the executor response in this round.">evaluators ${round.evaluator_count}</span>
        <span class="tooltip-anchor metric-chip" data-tooltip="Which scoring path was used for this round. Most rounds use peer council scores; some anchor rounds can use an objective answer check.">basis ${escapeHtml(scoringBasis)}</span>
      </div>
    `;
    roundsList.appendChild(item);
  }
}

async function refresh() {
  try {
    const data = await fetchJson("/api/market");
    renderModels(data.models || []);
    renderRounds(data.recent_rounds || []);
    warning.textContent = data.provisional
      ? "Provisional market state: the pool is still in bootstrap and early prices are noisy."
      : "Pool-relative market: prices are comparable within this pool only.";
    warning.classList.remove("hidden");
  } catch (error) {
    warning.textContent = error.message;
    warning.classList.remove("hidden");
  }
}

async function runRoundBatch(url) {
  warning.textContent = "Running rounds...";
  warning.classList.remove("hidden");
  try {
    await fetchJson(url, { method: "POST" });
    await refresh();
  } catch (error) {
    warning.textContent = error.message;
  }
}

document.getElementById("refresh").addEventListener("click", refresh);
document.getElementById("run-round").addEventListener("click", () => runRoundBatch("/api/rounds/run"));
document.getElementById("run-batch").addEventListener("click", () => runRoundBatch("/api/rounds/run-batch?count=3"));

refresh();
