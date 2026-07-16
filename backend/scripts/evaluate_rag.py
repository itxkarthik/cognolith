from __future__ import annotations

from pathlib import Path

from app.ai.evaluation import average_metric, evaluate_case, load_evaluation_cases


def main() -> int:
    dataset_path = Path(__file__).parents[1] / "evals" / "rag_cases.json"
    results = [evaluate_case(case) for case in load_evaluation_cases(dataset_path)]
    metrics = {
        "precision": average_metric(results, "precision"),
        "recall": average_metric(results, "recall"),
        "reciprocal_rank": average_metric(results, "reciprocal_rank"),
        "citation_validity": average_metric(results, "citation_validity"),
        "uncited_reference_rate": average_metric(results, "uncited_reference_rate"),
    }

    for result in results:
        print(
            f"{result.category:10} {result.name}: "
            f"precision={result.precision:.2f} recall={result.recall:.2f} "
            f"mrr={result.reciprocal_rank:.2f}"
        )
    print("\nAggregate")
    for name, value in metrics.items():
        print(f"{name}={value:.3f}")

    passes = (
        metrics["precision"] >= 0.85
        and metrics["recall"] >= 0.85
        and metrics["reciprocal_rank"] >= 0.90
        and metrics["citation_validity"] == 1.0
        and metrics["uncited_reference_rate"] == 0.0
    )
    return 0 if passes else 1


if __name__ == "__main__":
    raise SystemExit(main())
