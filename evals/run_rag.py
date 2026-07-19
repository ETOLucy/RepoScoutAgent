from __future__ import annotations

import argparse
import json
from pathlib import Path

from .run_baseline import DEFAULT_CASES, ROOT, evaluate

DEFAULT_OUTPUT = ROOT / "rag_report.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline hybrid RRF + MMR evaluation")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--input-price-per-million", type=float)
    parser.add_argument("--output-price-per-million", type=float)
    args = parser.parse_args()
    report = evaluate(
        args.cases,
        input_price_per_million=args.input_price_per_million,
        output_price_per_million=args.output_price_per_million,
        pipeline="hybrid_top_k",
    )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
