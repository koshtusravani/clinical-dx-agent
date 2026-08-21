"""
I wrote these tests to check my diagnostic tools read case data correctly
and fail the right way when data is missing. I use a small fixture file
under data/processed instead of mocking, so I'm testing against the real
schema my flatten_case.py script produces.
"""

import pytest

from src.failure_taxonomy import PermanentError
from src.tools.diagnostic_tools import conclude_diagnosis, escalate, order_test


def test_order_test_returns_existing_observation():
    result = order_test(patient_id="test-patient-001", test_name="fasting_glucose")
    assert result["value"] == 182
    assert result["unit"] == "mg/dL"


def test_order_test_raises_permanent_error_for_missing_test():
    with pytest.raises(PermanentError):
        order_test(patient_id="test-patient-001", test_name="tsh")


def test_order_test_raises_permanent_error_for_unknown_patient():
    with pytest.raises(PermanentError):
        order_test(patient_id="does-not-exist", test_name="fasting_glucose")


def test_conclude_diagnosis_packages_decision():
    result = conclude_diagnosis(
        condition="Type 2 Diabetes Mellitus",
        confidence=0.92,
        reasoning="fasting glucose and hba1c both confirm diabetes",
    )
    assert result["condition"] == "Type 2 Diabetes Mellitus"
    assert result["confidence"] == 0.92


def test_escalate_packages_reason():
    result = escalate(reason="conflicting evidence after step budget exhausted")
    assert result["escalated"] is True
    assert "conflicting evidence" in result["reason"]