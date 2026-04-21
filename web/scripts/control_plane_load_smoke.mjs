#!/usr/bin/env node

const baseUrl = (process.env.CLAWGRAPH_API_TEST_BASE_URL || "http://127.0.0.1:3402").replace(/\/$/, "");
const endpoint = `${baseUrl}/dashboard/bundle`;
const iterations = Number(process.env.CLAWGRAPH_BUNDLE_SMOKE_ITERATIONS || "10");
const p95BudgetMs = Number(process.env.CLAWGRAPH_BUNDLE_P95_BUDGET_MS || "1500");

function percentile(values, ratio) {
  if (!values.length) {
    return 0;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * ratio) - 1));
  return sorted[index];
}

const durations = [];
for (let index = 0; index < iterations; index += 1) {
  const startedAt = performance.now();
  const response = await fetch(endpoint, {
    headers: {
      Accept: "application/json"
    }
  });
  const elapsed = performance.now() - startedAt;
  if (!response.ok) {
    const payload = await response.text();
    console.error(JSON.stringify({
      ok: false,
      iteration: index + 1,
      status: response.status,
      payload
    }, null, 2));
    process.exit(1);
  }
  durations.push(elapsed);
}

const p50 = percentile(durations, 0.5);
const p95 = percentile(durations, 0.95);
const result = {
  ok: p95 <= p95BudgetMs,
  endpoint,
  iterations,
  p50Ms: Number(p50.toFixed(2)),
  p95Ms: Number(p95.toFixed(2)),
  maxMs: Number(Math.max(...durations).toFixed(2)),
  budgetMs: p95BudgetMs
};

if (!result.ok) {
  console.error(JSON.stringify(result, null, 2));
  process.exit(1);
}

console.log(JSON.stringify(result, null, 2));
