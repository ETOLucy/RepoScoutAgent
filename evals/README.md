# Offline Evaluation

[English](README.md) | [简体中文](README.zh-CN.md)

`baseline_cases.json` contains 15 manually labelled natural-language search cases. Each case fixes the parsed intent, GitHub Search repositories, Tree paths and Contents text, model assessments, relevant repositories, and expected evidence requirements. Document-map keys are the recorded Tree paths and their values are the recorded Contents responses.

Run the current full-document baseline without network access:

```powershell
.\.venv\Scripts\python.exe -m evals.run_baseline
```

The command writes `baseline_report.json` with quality, latency, model-call, GitHub-call, and estimated-token metrics. Token counts are deterministic character-based estimates for relative comparisons. Cost remains `null` because this repository uses a configurable model/provider and does not yet have a versioned price table; a fabricated public-model price is less useful than an explicit unconfigured value.

When the configured provider price is known, calculate the estimate explicitly:

```powershell
.\.venv\Scripts\python.exe -m evals.run_baseline `
  --input-price-per-million 1.00 `
  --output-price-per-million 2.00
```

The prices above are syntax examples, not assumed prices for `gpt-5.5`.

Known failure cases are intentionally retained. Future hybrid retrieval, reranking, or query-planning changes must run against the same fixtures and report improvements and regressions.

Search-stage evaluation is implemented in `evals/search_quality.py`. It reports candidate recall before reranking, Recall@24 after the inspection cutoff, NDCG@24, repositories never discovered, and relevant repositories dropped before document inspection. This separation prevents a final recommendation metric from hiding whether a failure came from query hypotheses or the 60-to-24 reduction. Relevance accepts graded labels rather than only a single gold repository, so several valid projects and degrees of fit can be represented.

Task-contract evaluation should additionally label atomic success criteria and whether each generated hard requirement was grounded in the user request. Open-ended hypothesis quality should be judged by observable candidate gain and redundancy, with a calibrated evidence-bound LLM judge used only for qualities that deterministic labels cannot express.

Run the hybrid BM25 + multi-query dense + RRF + MMR variant against the same fixtures:

```powershell
.\.venv\Scripts\python.exe -m evals.run_rag
```

The command writes `rag_report.json`. The replay uses deterministic local embeddings so it remains offline; production uses the model configured by `OPENAI_EMBEDDING_MODEL`. Set `REPOSCOUT_RETRIEVAL_MODE=semantic` only for dense-only ablation.
