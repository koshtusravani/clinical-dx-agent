"""
I wrote these tests to check my per-condition budget lookup falls back
correctly when I don't have data on a condition yet.
"""

from src.agent.budgets import DEFAULT_STEP_BUDGET, get_step_budget


def test_known_condition_returns_its_specific_budget():
    assert get_step_budget("Type 2 Diabetes Mellitus") == 2
    assert get_step_budget("Hypertension") == 1


def test_unknown_condition_falls_back_to_default():
    assert get_step_budget("Some Rare Condition Not In My Table") == DEFAULT_STEP_BUDGET


def test_no_suspected_condition_falls_back_to_default():
    assert get_step_budget(None) == DEFAULT_STEP_BUDGET