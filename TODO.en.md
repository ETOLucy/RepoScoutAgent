# RepoScoutAgent Roadmap

[简体中文](TODO.md) | [English](TODO.en.md)

This file lists unfinished work only. See [README.en.md](README.en.md) for current capabilities,
[docs/PERFORMANCE_STAR.en.md](docs/PERFORMANCE_STAR.en.md) for performance history, and
[docs/PERFORMANCE_MILESTONE.en.md](docs/PERFORMANCE_MILESTONE.en.md) for acceptance criteria.

## Priority 1: Retrieval and Code-Understanding Evaluation

- [ ] Expand the labelled set to 30-50 realistic natural-language requests.
- [ ] Measure Candidate Recall@50 and reranking gain on cases with 25-60 candidates.
- [ ] Track Success@5, NDCG@5, hard-constraint violations, and unsupported inference rate.
- [ ] Label task-parsing, candidate-recall, evidence-recall, and final-ranking failures separately.
- [ ] Add regressions for negation, deprecation, roadmap-only claims, and wrong product categories.
- [ ] Create labelled repository-level summaries for Deep Code and measure module/citation accuracy.
- [ ] Evaluate AST-aware symbol extraction for additional languages before adding a dependency.

## Priority 2: Performance Engineering

- [ ] Establish reproducible cold/warm-cache p50, p95, TTFC, and TTFV baselines.
- [ ] Record trace IDs, external calls, tokens, cost, and cache hit rates.
- [ ] Stream each repository as soon as its verified result is ready.
- [ ] Reuse candidates, documents, and evidence decisions across conversation turns safely.
- [ ] Evaluate the quality/latency Pareto of adaptive 6/8/12/24 assessment budgets.
- [ ] Benchmark Deep Code independently from normal search latency.
- [ ] Add code-snapshot caching keyed by repository commit and inspection budget.

## Priority 3: Maintainability

- [ ] Consolidate GitHub, document, model, and Deep Code runtime settings into typed settings.
- [ ] Replace broad `dict[str, Any]` node contracts with more precise typed models.
- [ ] Keep requirement verification, discovery, assessment, and code understanding as separate
  ownership boundaries.
- [ ] Add automated checks that every user-facing document has a working language counterpart.

## Definition of Done

A feature enters the main path only when it:

1. fixes a reproducible labelled failure or materially improves quality, latency, or cost;
2. exposes failures and fallback states to users;
3. does not cross the static-analysis safety boundary;
4. passes Ruff, mypy, pytest, coverage, and Docker build checks; and
5. appends performance evidence without overwriting historical baselines.
