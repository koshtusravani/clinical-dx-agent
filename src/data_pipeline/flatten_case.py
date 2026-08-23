"""
I convert a raw Synthea FHIR bundle into my own simplified case schema:

{
  "patient_id": "...",
  "age": 58,
  "conditions": ["Hypertension", "Chronic kidney disease stage 2"],
  "medications": ["Lisinopril"],
  "observations": {
    "fasting_glucose": {"value": 182, "unit": "mg/dL", "date": "..."},
    "hba1c": {"value": 8.1, "unit": "%", "date": "..."},
    ...
  },
  "ground_truth_condition": "Type 2 Diabetes Mellitus"
}

I keep this intentionally lossy, I only keep what my agent's tools need:
test lookups, medication list, conditions for ground truth and safety
checks. I run this once per generated Synthea batch to produce
data/processed/*.json.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
from datetime import date

from src.data_pipeline.synthea_loader import extract_resources, list_raw_bundles, load_bundle

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# I map a friendly test name, what my order_test tool asks for, to the
# LOINC display text Synthea uses in Observation.code.text. I expand this
# as I cover more conditions in my scope.
TEST_NAME_MAP = {
    "fasting_glucose": "Glucose",
    "hba1c": "Hemoglobin A1c/Hemoglobin.total in Blood",
    "cbc": "Hemoglobin [Mass/volume] in Blood",
    "creatinine": "Creatinine [Mass/volume] in Serum or Plasma",
    "cholesterol_total": "Cholesterol [Mass/volume] in Serum or Plasma",
    "cholesterol_ldl": "Cholesterol in LDL [Mass/volume] in Serum or Plasma by Direct assay",
    "urine_leukocyte_esterase": "Leukocyte esterase [Presence] in Urine by Test strip",
    "urine_nitrite": "Nitrite [Presence] in Urine by Test strip",
}


def _calc_age(birth_date_str: str) -> int:
    birth = date.fromisoformat(birth_date_str)
    today = date.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


# I map the condition names I care about to how they're likely to appear in
# Synthea's Condition.code.text. I search for these explicitly instead of
# trusting the first Condition resource, since Synthea logs many
# administrative and social findings as Condition resources too.
TARGET_CONDITIONS = {
    "Type 2 Diabetes Mellitus": ["diabetes"],
    "Anemia": ["anemia"],
    "Hypertension": ["hypertension"],
    "Urinary Tract Infection": ["urinary tract infection"],
    "Hyperlipidemia": ["hyperlipidemia"],
}


def _find_target_condition(condition_names: list[str]) -> str | None:
    """
    I search a patient's full condition list for anything matching one of
    my target diagnoses. I return the first match, or None if this patient
    doesn't have any of the conditions in my v1 scope.
    """
    lowered = [c.lower() for c in condition_names]
    for target_condition, keywords in TARGET_CONDITIONS.items():
        for keyword in keywords:
            if any(keyword in c for c in lowered):
                return target_condition
    return None


def flatten_bundle(bundle: dict) -> dict:
    patients = extract_resources(bundle, "Patient")
    if not patients:
        raise ValueError("No Patient resource found in bundle")
    patient = patients[0]

    conditions = extract_resources(bundle, "Condition")
    medications = extract_resources(bundle, "MedicationRequest")
    observations = extract_resources(bundle, "Observation")

    obs_by_test = {}
    for obs in observations:
        text = obs.get("code", {}).get("text", "")
        value = obs.get("valueQuantity", {})
        for friendly_name, loinc_text in TEST_NAME_MAP.items():
            if loinc_text.lower() in text.lower():
                obs_by_test[friendly_name] = {
                    "value": value.get("value"),
                    "unit": value.get("unit"),
                    "date": obs.get("effectiveDateTime"),
                }

    condition_names = [c.get("code", {}).get("text", "Unknown condition") for c in conditions]
    medication_names = [
        m.get("medicationCodeableConcept", {}).get("text", "Unknown medication")
        for m in medications
    ]

    return {
        "patient_id": patient.get("id"),
        "age": _calc_age(patient["birthDate"]) if patient.get("birthDate") else None,
        "conditions": condition_names,
        "medications": medication_names,
        "observations": obs_by_test,
        "ground_truth_condition": _find_target_condition(condition_names),
    }

def flatten_all():
    bundles = list_raw_bundles()
    if not bundles:
        print("I didn't find any raw bundles. Generate Synthea output and copy the JSON files into data/synthea_raw/ first.")
        return

    count = 0
    skipped = 0
    for path in bundles:
        try:
            bundle = load_bundle(path)
            flat = flatten_bundle(bundle)
            out_path = PROCESSED_DIR / f"{flat['patient_id']}.json"
            with open(out_path, "w") as f:
                json.dump(flat, f, indent=2)
            count += 1
        except Exception as e:
            skipped += 1

    print(f"I flattened {count} patient records into {PROCESSED_DIR}")
    print(f"I skipped {skipped} files that weren't patient bundles.")


if __name__ == "__main__":
    flatten_all()