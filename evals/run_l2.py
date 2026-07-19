from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.reposcout.evidence import validate_implementation_evidence
from src.reposcout.search.models import CriterionMatch, RepositoryAssessment

ROOT = Path(__file__).resolve().parent
DEFAULT_CASES = ROOT / "l2_cases.json"
DEFAULT_OUTPUT = ROOT / "l2_report.json"


def evaluate(cases_path: Path = DEFAULT_CASES) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(cases_path.read_text(encoding="utf-8"))
    results: list[dict[str, str]] = []
    for case in payload["cases"]:
        assessment = RepositoryAssessment(
            summary=case["id"],
            criteria=[
                CriterionMatch(
                    requirement_id="feature",
                    status=case["document_status"],
                    implementation_status=case["predicted"],
                    implementation_evidence=case["evidence"],
                    implementation_source_path=case["path"],
                    implementation_source_commit_sha="fixture-sha" if case["path"] else None,
                )
            ],
        )
        documents = []
        if case["path"]:
            documents.append(
                {
                    "path": case["path"],
                    "source_type": case["source_type"],
                    "content": case["content"],
                    "commit_sha": "fixture-sha",
                }
            )
        validated = validate_implementation_evidence(assessment, documents)
        actual = validated.criteria[0].implementation_status
        results.append({"id": case["id"], "expected": case["expected"], "actual": actual})

    implemented_predictions = [item for item in results if item["actual"] == "implemented"]
    correct_implemented = sum(
        item["expected"] == "implemented" for item in implemented_predictions
    )
    documented_cases = [item for item in results if item["expected"] == "documented_only"]
    return {
        "version": payload["version"],
        "case_count": len(results),
        "metrics": {
            "l2_precision": round(
                correct_implemented / max(1, len(implemented_predictions)), 4
            ),
            "documented_only_detection": round(
                sum(item["actual"] == "documented_only" for item in documented_cases)
                / max(1, len(documented_cases)),
                4,
            ),
            "false_implementation_rate": round(
                sum(
                    item["actual"] == "implemented" and item["expected"] != "implemented"
                    for item in results
                )
                / max(1, len(results)),
                4,
            ),
        },
        "results": results,
    }


def main() -> None:
    report = evaluate()
    DEFAULT_OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
