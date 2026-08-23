"""
I build my eval gold set here: a reproducible, balanced sample of cases
across my 5 target conditions. I cap every condition at my smallest
condition's usable count, so my eval report isn't secretly dominated by
whichever condition happens to have the most data.
"""

import json
import random
from pathlib import Path

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
GOLD_SETS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "gold_sets"
GOLD_SETS_DIR.mkdir(parents=True, exist_ok=True)

TARGET_CONDITIONS = [
    "Type 2 Diabetes Mellitus",
    "Anemia",
    "Hypertension",
    "Urinary Tract Infection",
    "Hyperlipidemia",
]

REQUIRED_OBSERVATIONS = {
    "Type 2 Diabetes Mellitus": ["fasting_glucose", "hba1c"],
    "Anemia": ["cbc"],
    "Hypertension": [],
    "Urinary Tract Infection": ["urine_leukocyte_esterase", "urine_nitrite"],
    "Hyperlipidemia": ["cholesterol_total", "cholesterol_ldl"],
}

RANDOM_SEED = 42


def _load_usable_cases_by_condition() -> dict[str, list[str]]:
    """
    I scan every processed case and group patient_ids by their ground
    truth condition, keeping only cases that have the observations
    required to actually diagnose that condition.
    """
    cases_by_condition = {c: [] for c in TARGET_CONDITIONS}

    for path in PROCESSED_DIR.glob("*.json"):
        with open(path) as f:
            case = json.load(f)

        gt = case.get("ground_truth_condition")
        if gt not in TARGET_CONDITIONS:
            continue

        required = REQUIRED_OBSERVATIONS.get(gt, [])
        obs = case.get("observations", {})
        if all(test in obs for test in required):
            cases_by_condition[gt].append(case["patient_id"])

    return cases_by_condition


def build_gold_set(sample_size: int | None = None) -> dict:
    """
    I build a balanced gold set by sampling sample_size cases from each
    condition. If sample_size is None, I use the smallest condition's
    usable count as the cap, so every condition is equally represented.
    """
    random.seed(RANDOM_SEED)
    cases_by_condition = _load_usable_cases_by_condition()

    if sample_size is None:
        sample_size = min(len(ids) for ids in cases_by_condition.values())

    gold_set = {}
    for condition, patient_ids in cases_by_condition.items():
        n = min(sample_size, len(patient_ids))
        gold_set[condition] = sorted(random.sample(patient_ids, n))

    return gold_set


def save_gold_set(gold_set: dict, filename: str = "diagnostic_gold.json"):
    out_path = GOLD_SETS_DIR / filename
    with open(out_path, "w") as f:
        json.dump(gold_set, f, indent=2)
    return out_path


if __name__ == "__main__":
    gold_set = build_gold_set()
    path = save_gold_set(gold_set)

    print(f"I built a gold set and saved it to {path}")
    for condition, patient_ids in gold_set.items():
        print(f"  {condition}: {len(patient_ids)} cases")