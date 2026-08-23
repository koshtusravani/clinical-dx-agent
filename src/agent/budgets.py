"""
I set a diagnostic step budget per condition here instead of one global
number. Some conditions genuinely confirm in two steps, others reasonably
need more. My eval harness checks whether my agent stayed within the
clinically reasonable budget for whatever condition it was actually working
toward, which is a more honest efficiency metric than a single fixed cap.
"""

# I calibrated these based on how many confirmatory tests a real workup for
# each condition typically needs. I expand this table as I add more
# conditions to my v1 scope.
STEP_BUDGET_BY_CONDITION = {
    "Type 2 Diabetes Mellitus": 2,   # fasting glucose + hba1c usually confirms it
    "Anemia": 2,                     # cbc + a follow up like ferritin
    "Hypertension": 1,               # often confirmed by vitals alone plus history
    "Urinary Tract Infection": 2,    # urinalysis + culture
    "Hyperlipidemia": 1,             # lipid panel alone usually confirms it
}

# I use this when the agent hasn't converged on a specific condition yet, or
# when I'm working with a condition not in my table.
DEFAULT_STEP_BUDGET = 4


def get_step_budget(suspected_condition: str | None) -> int:
    """
    I look up the step budget for whatever condition the agent's current
    top differential suggests. I fall back to the default budget if I don't
    have a suspected condition yet, since the agent's first step happens
    before it has any differential at all.
    """
    if suspected_condition is None:
        return DEFAULT_STEP_BUDGET
    return STEP_BUDGET_BY_CONDITION.get(suspected_condition, DEFAULT_STEP_BUDGET)