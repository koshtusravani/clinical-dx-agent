"""
I run my full pipeline, diagnostic loop into safety loop, against my gold
set and produce an eval report: accuracy, steps to diagnosis, cost,
latency, and failure breakdown, all broken down per condition.

I support a --limit flag so I can run a small subset while developing or
debugging this script, without burning through my full gold set on every
iteration.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.agent.diagnostic_loop import run_diagnostic_loop
from src.agent.safety_loop import run_safety_loop

GOLD_SET_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "gold_sets" / "diagnostic_gold.json"
PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "gold_sets"

# I map each condition to the symptoms I present to my agent, since my
# processed case data doesn't carry presenting symptoms, only conditions,
# medications, and observations. I hand write a representative symptom set
# per condition, matching how each would realistically present.
PRESENTING_SYMPTOMS = {
    "Type 2 Diabetes Mellitus": ["fatigue", "increased thirst", "frequent urination"],
    "Anemia": ["fatigue", "pallor", "shortness of breath on exertion"],
    "Hypertension": ["headache", "occasional dizziness"],
    "Urinary Tract Infection": ["burning with urination", "urinary frequency", "pelvic discomfort"],
    "Hyperlipidemia": ["no acute symptoms, routine screening"],
}


def load_gold_set() -> dict:
    with open(GOLD_SET_PATH) as f:
        return json.load(f)


def run_single_case(patient_id: str, condition: str) -> dict:
    """
    I run one case through my full pipeline and grade the outcome against
    ground truth. I catch any unexpected exception here so one bad case
    doesn't kill the whole eval run, and I record it as a run-level error
    instead.
    """
    symptoms = PRESENTING_SYMPTOMS.get(condition, ["fatigue"])

    try:
        state = run_diagnostic_loop(patient_id=patient_id, presenting_symptoms=symptoms)

        if state.phase == "treatment_safety":
            state = run_safety_loop(state)

        diagnosis_correct = None
        if state.final_diagnosis is not None:
            # I do a loose substring match rather than exact string equality,
            # since my agent might phrase a correct diagnosis slightly
            # differently from my ground truth label, for example "Diabetes
            # Mellitus" versus "Type 2 Diabetes Mellitus".
            diagnosis_correct = _condition_matches(state.final_diagnosis, condition)

        return {
            "patient_id": patient_id,
            "ground_truth": condition,
            "final_diagnosis": state.final_diagnosis,
            "diagnosis_correct": diagnosis_correct,
            "escalated": state.escalated,
            "escalation_reason": state.escalation_reason,
            "failure_category": state.failure_category.value if hasattr(state.failure_category, "value") else state.failure_category,
            "steps_to_diagnosis": state.steps_to_diagnosis(),
            "safety_classification": state.safety_classification,
            "total_cost_usd": state.total_cost_usd(),
            "total_latency_ms": state.total_latency_ms(),
            "run_error": None,
        }

    except Exception as e:
        return {
            "patient_id": patient_id,
            "ground_truth": condition,
            "final_diagnosis": None,
            "diagnosis_correct": None,
            "escalated": None,
            "escalation_reason": None,
            "failure_category": "run_error",
            "steps_to_diagnosis": None,
            "safety_classification": None,
            "total_cost_usd": 0,
            "total_latency_ms": 0,
            "run_error": str(e),
        }


def _condition_matches(predicted: str, ground_truth: str) -> bool:
    """
    I check a loose match between my agent's stated diagnosis and my
    ground truth label. I strip common qualifiers like "Type 2" and check
    for meaningful keyword overlap rather than requiring an exact string
    match.
    """
    predicted_lower = predicted.lower()
    ground_truth_lower = ground_truth.lower()

    # I check the core condition keyword rather than the full label, since
    # my agent might say "Diabetes Mellitus" for a ground truth of "Type 2
    # Diabetes Mellitus".
    key_terms = {
        "Type 2 Diabetes Mellitus": ["diabetes"],
        "Anemia": ["anemia"],
        "Hypertension": ["hypertension"],
        "Urinary Tract Infection": ["urinary tract infection", "uti"],
        "Hyperlipidemia": ["hyperlipidemia", "dyslipidemia"],
    }
    terms = key_terms.get(ground_truth, [ground_truth_lower])
    return any(term in predicted_lower for term in terms)


def run_eval(limit_per_condition: int | None = None) -> list[dict]:
    gold_set = load_gold_set()
    results = []

    for condition, patient_ids in gold_set.items():
        ids_to_run = patient_ids[:limit_per_condition] if limit_per_condition else patient_ids
        print(f"\nRunning {len(ids_to_run)} cases for {condition}...")

        for i, patient_id in enumerate(ids_to_run, 1):
            print(f"  [{i}/{len(ids_to_run)}] {patient_id}...", end=" ", flush=True)
            result = run_single_case(patient_id, condition)
            results.append(result)

            status = "OK" if result["diagnosis_correct"] else ("ESCALATED" if result["escalated"] else "MISS")
            print(status)

    return results


def save_results(results: list[dict], filename: str = "eval_run_results.json") -> Path:
    out_path = RESULTS_DIR / filename
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="I run my diagnostic eval against the gold set.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of cases per condition, for quick test runs.")
    args = parser.parse_args()

    results = run_eval(limit_per_condition=args.limit)
    out_path = save_results(results)

    print(f"\nSaved {len(results)} results to {out_path}")