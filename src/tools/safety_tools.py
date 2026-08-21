"""
I define my treatment safety tools here. For v1 I use a small, hand curated
local lookup table for drug interactions and dosage rules rather than a live
API, so my eval results stay deterministic and reproducible. I plan to swap
in a real OpenFDA integration later as a stretch feature, once my core loop
is proven solid.
"""

import json
from pathlib import Path

from src.failure_taxonomy import PermanentError

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"

# I hand curated this interaction table for my v1 gold set. Severity levels
# are "none", "minor", "moderate", "severe".
INTERACTION_TABLE = {
    frozenset({"metformin", "lisinopril"}): {
        "severity": "none",
        "description": "I found no significant interaction between these two drugs.",
    },
    frozenset({"metformin", "contrast_dye"}): {
        "severity": "severe",
        "description": "I flag this combination because contrast dye raises the risk of lactic acidosis in patients taking metformin.",
    },
    frozenset({"warfarin", "aspirin"}): {
        "severity": "severe",
        "description": "I flag this combination because combining these significantly raises bleeding risk.",
    },
    frozenset({"lisinopril", "ibuprofen"}): {
        "severity": "moderate",
        "description": "I flag this combination because NSAIDs can reduce the effectiveness of ACE inhibitors and stress the kidneys.",
    },
}

# I use this to flag drugs that need dosage adjustment based on renal function.
RENAL_ADJUSTMENT_DRUGS = {"metformin", "gabapentin"}


def _load_case(patient_id: str) -> dict:
    path = PROCESSED_DIR / f"{patient_id}.json"
    if not path.exists():
        raise PermanentError(f"I couldn't find a processed case file for patient_id {patient_id}")
    with open(path) as f:
        return json.load(f)


def get_patient_history(patient_id: str) -> dict:
    """
    I pull the patient's existing medications, conditions, and age here.
    This is the one point in my whole pipeline where I look at history, and
    I only do it once I've already reached a diagnosis and need to check a
    proposed treatment's safety.
    """
    case = _load_case(patient_id)
    return {
        "medications": case.get("medications", []),
        "conditions": case.get("conditions", []),
        "age": case.get("age"),
    }


def check_drug_interaction(drug_a: str, drug_b: str) -> dict:
    """
    I check my local interaction table for a pair of drugs. If I don't have
    data on this specific pair, I say so explicitly rather than assuming
    it's safe, since silently assuming safety would be a dangerous default.
    """
    key = frozenset({drug_a.lower(), drug_b.lower()})
    if key in INTERACTION_TABLE:
        return INTERACTION_TABLE[key]

    return {
        "severity": "unknown",
        "description": f"I don't have interaction data for {drug_a} and {drug_b} in my local table. I recommend a clinician review this pair directly.",
    }


def check_dosage_adjustment(drug: str, patient_factors: dict) -> dict:
    """
    I check whether a drug needs a dosage adjustment based on patient
    factors like age or reduced kidney function. This is intentionally
    simple for v1, real dosage rules are far more nuanced than this table.
    """
    drug_lower = drug.lower()
    conditions = [c.lower() for c in patient_factors.get("conditions", [])]
    has_renal_impairment = any("kidney" in c or "renal" in c for c in conditions)

    if drug_lower in RENAL_ADJUSTMENT_DRUGS and has_renal_impairment:
        return {
            "adjustment_needed": True,
            "recommendation": f"I recommend reducing the starting dose of {drug} and monitoring kidney function, since this patient has documented renal impairment.",
        }

    return {
        "adjustment_needed": False,
        "recommendation": f"I don't see a dosage adjustment needed for {drug} based on the factors I checked.",
    }