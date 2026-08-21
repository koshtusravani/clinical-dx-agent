"""
I define the tools my diagnostic loop can call here. Each one reads from my
flattened Synthea case data and raises TransientError or PermanentError when
something goes wrong, so my retry wrapper in tools/base.py can handle it
consistently.
"""

import json
from pathlib import Path

from src.failure_taxonomy import PermanentError

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"


def _load_case(patient_id: str) -> dict:
    path = PROCESSED_DIR / f"{patient_id}.json"
    if not path.exists():
        raise PermanentError(f"I couldn't find a processed case file for patient_id {patient_id}")
    with open(path) as f:
        return json.load(f)


def order_test(patient_id: str, test_name: str) -> dict:
    """
    I look up a test result for a patient from their flattened Synthea case.
    If the patient doesn't have this observation recorded, I raise a
    PermanentError since retrying won't produce data that doesn't exist. My
    agent has to pick a different test in that situation, not retry this one.
    """
    case = _load_case(patient_id)
    observations = case.get("observations", {})

    if test_name not in observations:
        raise PermanentError(
            f"No {test_name} result is available for this patient. I need to pick a different test."
        )

    return observations[test_name]


def conclude_diagnosis(condition: str, confidence: float, reasoning: str) -> dict:
    """
    I use this as the terminal action for my diagnostic loop. It doesn't
    look anything up, it just packages the agent's decision into a
    structured record I can log and later grade against ground truth.
    """
    return {
        "condition": condition,
        "confidence": confidence,
        "reasoning": reasoning,
    }


def escalate(reason: str) -> dict:
    """
    I use this as the other terminal action for my diagnostic loop. My agent
    calls this instead of forcing a guess when it doesn't have confident
    evidence. I treat this as a distinct, valid outcome in my eval, not a
    failure.
    """
    return {
        "escalated": True,
        "reason": reason,
    }