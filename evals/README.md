# Offline Evaluation

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

Known failure cases are intentionally retained. Future BM25, Embedding, reranking, or query-planning changes must run against the same fixtures and report improvements and regressions.
