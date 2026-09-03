"""
I aggregate my raw eval_run_results.json into the summary report I put in
my README: a three-way diagnostic outcome breakdown (correct, incorrect,
appropriately escalated), steps to diagnosis, cost, and latency, all
broken down per condition, plus an overall summary and a failure category
breakdown.

I report escalation as a distinct, legitimate outcome rather than folding
it into a single "accuracy" number, since my agent is designed to defer
rather than guess when evidence is genuinely insufficient. A high
escalation rate on a condition with sparse lab data is a sign my agent is
calibrated correctly, not a sign it's failing.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

RESULTS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "gold_sets" / "eval_run_results.json"


def load_results() -> list[dict]:
    with open(RESULTS_PATH) as f:
        return json.load(f)


def _classify_outcome(case: dict) -> str:
    """
    I classify each case's diagnostic outcome here, independent of whether
    the safety phase later escalated. A correct diagnosis followed by a
    safety-phase escalation is still a correct diagnosis; the escalation
    is a separate, later judgment about treatment safety, not a diagnostic
    failure. I only classify a case as "escalated" here if my agent never
    reached a diagnosis at all, meaning it escalated during the diagnostic
    phase itself.
    """
    if case["run_error"] is not None:
        return "run_error"
    if case["diagnosis_correct"] is True:
        return "correct"
    if case["diagnosis_correct"] is False:
        return "incorrect"
    if case["escalated"] is True:
        return "escalated_no_diagnosis"
    return "unresolved"


def build_report(results: list[dict]) -> dict:
    by_condition = defaultdict(list)
    for r in results:
        by_condition[r["ground_truth"]].append(r)

    report = {"per_condition": {}, "overall": {}, "failure_breakdown": defaultdict(int)}

    for condition, cases in by_condition.items():
        n = len(cases)
        outcomes = [_classify_outcome(c) for c in cases]
        outcome_counts = {
            "correct": outcomes.count("correct"),
            "incorrect": outcomes.count("incorrect"),
            "escalated_no_diagnosis": outcomes.count("escalated_no_diagnosis"),
            "run_error": outcomes.count("run_error"),
            "unresolved": outcomes.count("unresolved"),
        }
        # I separately track how many of the CORRECT diagnoses still had
        # their proposed treatment escalated during safety-checking, since
        # that's a distinct, good-behavior signal, not a diagnostic failure.
        safety_escalated_after_correct = sum(
            1 for c in cases if c["diagnosis_correct"] is True and c["escalated"] is True
        )

        escalation_reasons = defaultdict(int)
        for c in cases:
            if c["escalated"] is True and c["failure_category"]:
                escalation_reasons[c["failure_category"]] += 1

        valid_steps = [c["steps_to_diagnosis"] for c in cases if c["steps_to_diagnosis"] is not None]
        valid_costs = [c["total_cost_usd"] for c in cases if c["total_cost_usd"] is not None]
        valid_latency = [c["total_latency_ms"] for c in cases if c["total_latency_ms"] is not None]

        report["per_condition"][condition] = {
            "n_cases": n,
            "correct_pct": round(100 * outcome_counts["correct"] / n, 1),
            "incorrect_pct": round(100 * outcome_counts["incorrect"] / n, 1),
            "escalated_no_diagnosis_pct": round(100 * outcome_counts["escalated_no_diagnosis"] / n, 1),
            "run_error_pct": round(100 * outcome_counts["run_error"] / n, 1),
            "safety_escalated_after_correct_dx": safety_escalated_after_correct,
            "escalation_reasons": dict(escalation_reasons),
            "avg_steps_to_diagnosis": round(sum(valid_steps) / len(valid_steps), 2) if valid_steps else None,
            "avg_cost_usd": round(sum(valid_costs) / len(valid_costs), 4) if valid_costs else None,
            "avg_latency_ms": round(sum(valid_latency) / len(valid_latency), 0) if valid_latency else None,
            "total_cost_usd": round(sum(valid_costs), 4),
        }

        for c in cases:
            if c["failure_category"]:
                report["failure_breakdown"][c["failure_category"]] += 1

    all_outcomes = [_classify_outcome(r) for r in results]
    all_costs = [r["total_cost_usd"] for r in results if r["total_cost_usd"] is not None]
    all_latency = [r["total_latency_ms"] for r in results if r["total_latency_ms"] is not None]
    all_safety_escalated_after_correct = sum(
        1 for r in results if r["diagnosis_correct"] is True and r["escalated"] is True
    )

    report["overall"] = {
        "n_cases": len(results),
        "correct_pct": round(100 * all_outcomes.count("correct") / len(results), 1),
        "incorrect_pct": round(100 * all_outcomes.count("incorrect") / len(results), 1),
        "escalated_no_diagnosis_pct": round(100 * all_outcomes.count("escalated_no_diagnosis") / len(results), 1),
        "run_error_pct": round(100 * all_outcomes.count("run_error") / len(results), 1),
        "safety_escalated_after_correct_dx": all_safety_escalated_after_correct,
        "total_cost_usd": round(sum(all_costs), 2),
        "avg_cost_usd": round(sum(all_costs) / len(all_costs), 4) if all_costs else None,
        "avg_latency_ms": round(sum(all_latency) / len(all_latency), 0) if all_latency else None,
    }

    report["failure_breakdown"] = dict(report["failure_breakdown"])
    return report


def print_report(report: dict):
    print("=" * 70)
    print("OVERALL")
    print("=" * 70)
    for k, v in report["overall"].items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 70)
    print("PER CONDITION")
    print("=" * 70)
    for condition, stats in report["per_condition"].items():
        print(f"\n{condition} (n={stats['n_cases']})")
        for k, v in stats.items():
            if k != "n_cases":
                print(f"  {k}: {v}")

    print("\n" + "=" * 70)
    print("FAILURE CATEGORY BREAKDOWN (across all escalated/error cases)")
    print("=" * 70)
    for category, count in sorted(report["failure_breakdown"].items(), key=lambda x: -x[1]):
        print(f"  {category}: {count}")


if __name__ == "__main__":
    results = load_results()
    report = build_report(results)
    print_report(report)

    out_path = Path(__file__).resolve().parent.parent.parent / "data" / "gold_sets" / "eval_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved full report to {out_path}")