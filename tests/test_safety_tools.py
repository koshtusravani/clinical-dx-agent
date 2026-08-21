"""
I wrote these tests to check my safety tools correctly identify known
interactions, correctly flag unknown pairs instead of assuming safety, and
correctly catch the renal impairment case that needs a dosage adjustment.
"""

import pytest

from src.failure_taxonomy import PermanentError
from src.tools.safety_tools import (
    check_dosage_adjustment,
    check_drug_interaction,
    get_patient_history,
)


def test_get_patient_history_returns_expected_fields():
    history = get_patient_history(patient_id="test-patient-001")
    assert history["medications"] == ["Lisinopril"]
    assert history["age"] == 58


def test_get_patient_history_raises_for_unknown_patient():
    with pytest.raises(PermanentError):
        get_patient_history(patient_id="does-not-exist")


def test_known_interaction_is_flagged_severe():
    result = check_drug_interaction("metformin", "contrast_dye")
    assert result["severity"] == "severe"


def test_known_safe_pair_returns_none_severity():
    result = check_drug_interaction("metformin", "lisinopril")
    assert result["severity"] == "none"


def test_interaction_check_is_order_independent():
    a_b = check_drug_interaction("warfarin", "aspirin")
    b_a = check_drug_interaction("aspirin", "warfarin")
    assert a_b["severity"] == b_a["severity"] == "severe"


def test_unknown_pair_returns_unknown_not_a_false_safe():
    result = check_drug_interaction("metformin", "some_untracked_drug")
    assert result["severity"] == "unknown"


def test_dosage_adjustment_flagged_for_renal_impairment():
    history = get_patient_history(patient_id="test-patient-002")
    result = check_dosage_adjustment(drug="metformin", patient_factors=history)
    assert result["adjustment_needed"] is True


def test_dosage_adjustment_not_flagged_without_renal_impairment():
    history = get_patient_history(patient_id="test-patient-001")
    result = check_dosage_adjustment(drug="metformin", patient_factors=history)
    assert result["adjustment_needed"] is False