"""
I use this script to see how many patients I have per target condition,
and whether they have the observations my diagnostic tools actually need,
before I build my eval gold set.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

# I mirror this from flatten_case.py so this script's counts always match
# what my flattening pipeline actually assigns as ground truth.
TARGET_CONDITIONS = [
    "Type 2 Diabetes Mellitus",
    "Anemia",
    "Hypertension",
    "Urinary Tract Infection",
    "Hyperlipidemia",
]

# I map each target condition to the tests my diagnostic loop would
# actually need to confirm it, so I can check real usability per condition,
# not just raw patient counts.
REQUIRED_OBSERVATIONS = {
    "Type 2 Diabetes Mellitus": ["fasting_glucose", "hba1c"],
    "Anemia": ["cbc"],
    "Hypertension": [],
    "Urinary Tract Infection": ["urine_leukocyte_esterase", "urine_nitrite"],
    "Hyperlipidemia": ["cholesterol_total", "cholesterol_ldl"],
}

all_files = list(PROCESSED_DIR.glob("*.json"))

ground_truth_counts = Counter()
usable_counts = Counter()

for path in all_files:
    with open(path) as f:
        case = json.load(f)

    gt = case.get("ground_truth_condition")
    if gt is None:
        continue

    ground_truth_counts[gt] += 1

    required = REQUIRED_OBSERVATIONS.get(gt, [])
    obs = case.get("observations", {})
    if all(test in obs for test in required):
        usable_counts[gt] += 1

print(f"Total patients: {len(all_files)}")
print(f"Patients with a target condition as ground truth: {sum(ground_truth_counts.values())}")

print("\nPer-condition breakdown (total with condition -> usable with required observations):")
for condition in TARGET_CONDITIONS:
    total = ground_truth_counts.get(condition, 0)
    usable = usable_counts.get(condition, 0)
    print(f"  {condition:30s}  total={total:4d}   usable={usable:4d}")