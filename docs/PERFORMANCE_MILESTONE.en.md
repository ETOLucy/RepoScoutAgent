# Performance Engineering v1

[简体中文](PERFORMANCE_MILESTONE.md) | [English](PERFORMANCE_MILESTONE.en.md)

## Goal

Reduce end-to-end search latency while preserving Recall@analysis, Success@5, NDCG@5, L2
precision, core-purpose precision, and citation accuracy. Establish reproducible cold/warm-cache
p50/p95, TTFC/TTFV, call/token/cost traces, and separate Deep Code latency reporting.

## Completed Foundation

- [x] `60 -> 24 -> 8` candidate funnel with bounded concurrent workers.
- [x] Per-repository failure isolation and explicit fallbacks.
- [x] Batched embeddings, content cache, and cross-request embedding circuit breaker.
- [x] Per-node timing in JSON and SSE progress.
- [x] Provisional candidates and analysis counts streamed early.
- [x] Dedicated requirement-parsing timeout with deterministic Chinese/English fallback.
- [x] Optional Deep Code node excluded from the default latency path.

## Proposed Work

1. **Reproducible cold/warm p50/p95 and external-call traces**  
   Freeze query plans, candidate responses, document SHAs, and code snapshots. Record TTFC, TTFV,
   node timings, call counts, tokens, cost, cache hits, and 429/5xx responses for at least ten runs.
2. **Progressive verified repository results**  
   Publish each citation-backed assessment as its worker completes while clearly distinguishing
   provisional and verified states.
3. **Safe conversation reuse**  
   Cache by task contract, repository SHA, model version, retrieval mode, and inspection budget.
4. **Adaptive assessment budget evaluation**  
   Compare 6/8/12/24 candidates and plot latency against Recall@analysis, Success@5, and NDCG@5.
5. **Deep Code benchmark**  
   Report normal-search latency separately from user-selected Deep Code latency. Evaluate small,
   medium, large, established, and truncated-tree repositories.

## Exit Criteria

- At least ten reproducible runs for cold and warm caches.
- Traceable TTFC, TTFV, node timings, external calls, tokens, and cost.
- Citation Accuracy `= 1.00`, Recall@analysis `>= 0.98`, and no L2 precision regression.
- No statistically stable Success@5 or NDCG@5 regression.
- Deep Code quote accuracy `= 1.00` on the labelled set.
- Results appended to the public performance archive `PERFORMANCE_HISTORY.md` without deleting
  historical baselines.

## GitHub Setup Note

This file is the version-controlled milestone definition. Creating the corresponding GitHub
Milestone and issues requires `Issues: Read and write` permission.
