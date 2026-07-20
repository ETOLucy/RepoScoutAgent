# RepoScoutAgent Performance Engineering Archive

[简体中文](PERFORMANCE_HISTORY.md) | [English](PERFORMANCE_HISTORY.en.md)

This is the English companion to the long-term performance archive. Historical baselines, failed
attempts, environment differences, and quality guardrails must remain visible; new results are
appended rather than replacing older numbers. The Chinese archive is the canonical fine-grained
run log, while this document provides the same decisions and principal measurements in English.

Last updated: 2026-07-20

## Executive Summary

An early broad GitHub-project request did not complete within a 300-second client budget. Candidate
funnels, bounded concurrency, model specialization, timeout isolation, and capability circuit
breakers reduced one observation of the same request to 100.6 seconds. Using 300 seconds as a
conservative lower bound, latency decreased by at least 66.5% and completion speed improved by at
least 2.98x.

This is a single real-network observation, not p50/p95 or throughput proof. The project therefore
keeps fixed offline quality gates and requires repeated controlled runs before treating an
optimization as a stable benchmark.

## Quality Guardrails at the Recorded Baseline

| Metric | Recorded value |
|---|---:|
| Recall@analysis | 1.00 |
| Citation Accuracy | 1.00 |
| Automated tests at that historical point | 52 passed |
| Coverage at that historical point | 87.05% |

Current test counts may be higher; historical values are not rewritten.

## Optimization Record

### Context

The service converts a natural-language request into several GitHub queries, reduces as many as 60
repositories, reads documentation and bounded source evidence from the top 24, and performs L1 and
L2 validation on a smaller analysis set. The original pipeline exceeded 300 seconds, and coarse UI
progress made the delay look like a disconnected service.

### Objective

Reduce end-to-end latency without weakening candidate recall, final ranking quality, L2 precision,
or citation accuracy. Failures and fallbacks had to remain visible rather than silently presenting
degraded output as fully model-verified.

### Changes

- Added a `60 -> 24 -> 8` candidate funnel with exploration slots.
- Replaced sequential or fixed-batch assessment with bounded stateless workers.
- Assigned faster structured assessment models where supported.
- Isolated each repository behind a finite model timeout.
- Batched embedding inputs and cached by model plus content hash.
- Added request-local and cross-request embedding capability circuit breakers.
- Preserved deterministic repository ranking and BM25 retrieval when embeddings were unavailable.
- Added phase-specific recall, NDCG, L2, and citation regressions.
- Added per-node timing and progressive provisional/analysis-count SSE events.

### Observed Result

| Version | Configuration | Observed end-to-end result |
|---|---|---:|
| Original | Up to 24 repositories assessed sequentially | `>300 s`, client timeout |
| First parallel version | `24 -> 12`, four fixed groups, embedding batch | still `>300 s` |
| Faster assessment model | 8 candidates, dynamic concurrency | `161.6 s` |
| Circuit-breaker version | 8 workers, 60-second isolation, embedding fallback | `100.6 s`, 7 results |

The actual original duration is unknown because it did not finish. Claims must therefore say "at
least 66.5%" rather than implying a precise full-run comparison.

## What Was Active in the 100.6-Second Run

The material active mechanisms were the candidate funnel, dynamic workers, model split, timeout
isolation, and embedding failure fallback. Embedding batching and cache existed but the configured
provider did not support embeddings in that run, so they cannot be credited for the measured gain.
Document caches may also have differed between observations.

## 2026-07-20 Similar-Project Search Observation

Query:

```text
Find open-source projects similar in product category to RepoScout: natural-language repository or
software discovery, multi-source search, project comparison, verifiable citations or research
reports, and local deployment.
```

The observation enabled GitHub plus the model but not SearXNG, so it did not exercise web discovery.

### Before

- Research ID: `0041aec0-e876-4732-954c-f5852b27c03e`
- End to end: `85.24 s`
- Requirement understanding: `34.33 s`
- GitHub search: `2.73 s`
- Repository ranking: `4.95 s`
- Document inspection: `21.47 s`
- Candidate assessment: `21.48 s`
- Semantic reranking failed with `InternalServerError`; deterministic ranking completed the run.
- Keyword-overlap false positives ranked highly, while RepoScout itself ranked fourth.

### Changes

- Added `--requirement-timeout`, defaulting to 15 seconds.
- Added deterministic Chinese/English concept extraction for timeout fallback.
- Added validated `core_purpose` evidence with quote, path, and commit SHA.
- Explicit core-purpose mismatch rejects a candidate; unknown purpose remains visible but penalized.
- Similarity reference names are removed from executable queries so `RepoScout` is context, not a
  repository-name search term.

### After

- Research ID: `f3aefa4c-65e8-45b8-b074-6d1cd4708f20`
- End to end: `76.02 s`, 9.22 seconds or about 9.1% lower in this single observation.
- Requirement understanding: `15.01 s` after a timeout and deterministic fallback.
- GitHub search: `3.20 s`
- Repository ranking: `6.21 s`
- Document inspection: `29.76 s`
- Candidate assessment: `21.34 s`
- RepoScout ranked first with validated core-purpose evidence.
- `vict0rsch/PaperMemory` was rejected as a product-category mismatch.

Document inspection increased materially, showing why this is observational rather than proof of a
stable 9.1% gain. One 3.27-second run was a total network fast failure and was excluded. A 71.53-
second run used an inadequate old fallback that retrieved same-name repositories and was excluded
because quality was not equivalent.

## Generic-AI Comparison Boundary

The planned no-tools generic-AI comparison was blocked by the execution environment's data-egress
policy. No result was fabricated. A generic model will usually produce prose faster, while
RepoScout's measurable differentiators are current repository snapshots, exact citations,
unknown/violated states, persistent research tasks, and multi-component compatibility evidence.

Future controlled evaluation should compare no-tools AI, web-enabled AI, and RepoScout using first-
token latency, repository existence, core-purpose correctness, citation accuracy, and freshness.

## Deep Code Measurement Policy

Deep Code is user-selected and intentionally adds latency. Its time must not be merged into the
default-search p50/p95. Report at least:

- repository size tier and selected budget;
- tree truncation state, total code files, files and characters read;
- deterministic versus model-assisted explanation;
- module quote accuracy and entry-point recall;
- code-snapshot cache state; and
- incremental latency after the normal recommendation result.

Established, small, medium, large, and truncated-tree repositories must be separate benchmark
groups. Deep Code explains code responsibilities; it is not an L3 build or L4 runtime probe.
