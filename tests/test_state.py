"""
I wrote these tests to check my AgentState tracks cost, latency, and step
counts correctly, since the eval harness depends on these being accurate.
"""

from src.agent.state import AgentState, StepRecord, DifferentialEntry


def test_empty_state_has_zero_totals():
    state = AgentState(run_id="test-1", patient_id="patient-1", presenting_symptoms=["fatigue"])
    assert state.total_cost_usd() == 0
    assert state.total_latency_ms() == 0
    assert state.steps_to_diagnosis() == 0


def test_totals_accumulate_across_steps():
    state = AgentState(run_id="test-2", patient_id="patient-2", presenting_symptoms=["thirst"])
    state.steps_taken.append(StepRecord(
        step_num=1, action="order_test", tool_called="order_test",
        args={"test_name": "fasting_glucose"}, result={"value": 182},
        reasoning="checking for diabetes", latency_ms=120.0, cost_usd=0.001,
        retry_count=0, status="success",
    ))
    state.steps_taken.append(StepRecord(
        step_num=2, action="order_test", tool_called="order_test",
        args={"test_name": "hba1c"}, result={"value": 8.1},
        reasoning="confirming diabetes", latency_ms=95.0, cost_usd=0.001,
        retry_count=0, status="success",
    ))

    assert state.total_cost_usd() == 0.002
    assert state.total_latency_ms() == 215.0
    assert state.steps_to_diagnosis() == 2


def test_conclude_diagnosis_step_not_counted_as_test():
    state = AgentState(run_id="test-3", patient_id="patient-3", presenting_symptoms=["fatigue"])
    state.steps_taken.append(StepRecord(
        step_num=1, action="conclude_diagnosis", tool_called="conclude_diagnosis",
        args={}, result={"condition": "Type 2 Diabetes"},
        reasoning="confident based on two tests", latency_ms=50.0, cost_usd=0.0005,
        retry_count=0, status="success",
    ))
    assert state.steps_to_diagnosis() == 0


def test_differential_entry_holds_confidence():
    entry = DifferentialEntry(condition="Type 2 Diabetes", confidence=0.9, reasoning="glucose and hba1c both high")
    assert entry.confidence == 0.9
    assert entry.condition == "Type 2 Diabetes"