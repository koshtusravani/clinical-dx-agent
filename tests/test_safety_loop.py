"""
I wrote these tests to verify my safety loop's control flow: does it walk
through propose, history, interaction check, dosage check, and classify
correctly, does it escalate on a severe interaction, and does it stop if
it runs out of steps. I mock call_llm here for the same reasons as my
diagnostic loop tests: fast, free, deterministic.

I already verified this loop works correctly against the real Anthropic
API in my live test script, chained directly after the diagnostic loop.
"""

from unittest.mock import MagicMock, patch

from src.agent.safety_loop import run_safety_loop
from src.agent.state import AgentState


def _make_fake_response(tool_name: str, tool_input: dict, text: str = ""):
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.input = tool_input
    tool_block.id = "fake_tool_use_id"

    response = MagicMock()
    if text:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = text
        response.content = [text_block, tool_block]
    else:
        response.content = [tool_block]
    return response


def _fake_llm_meta():
    return {
        "latency_ms": 500.0,
        "cost_usd": 0.001,
        "model": "claude-sonnet-4-6",
        "input_tokens": 100,
        "output_tokens": 50,
    }


def _make_diagnosed_state():
    """
    I build a state that's already past the diagnostic phase, matching
    what my diagnostic loop hands off when it reaches treatment_safety.
    """
    state = AgentState(
        run_id="test-run",
        patient_id="test-patient-001",
        presenting_symptoms=["fatigue"],
    )
    state.final_diagnosis = "Type 2 Diabetes Mellitus"
    state.diagnosis_confidence = 0.95
    state.phase = "treatment_safety"
    return state


@patch("src.agent.safety_loop.call_llm")
def test_safety_loop_full_happy_path(mock_call_llm):
    """
    I check that my safety loop walks through all five expected steps in
    order and lands on a safe classification, mirroring the real metformin
    plus lisinopril case I already verified live.
    """
    mock_call_llm.side_effect = [
        (_make_fake_response("propose_treatment", {"drug": "Metformin", "reasoning": "first line for T2DM"}), _fake_llm_meta()),
        (_make_fake_response("get_patient_history", {}), _fake_llm_meta()),
        (_make_fake_response("check_drug_interaction", {"drug_b": "Lisinopril"}), _fake_llm_meta()),
        (_make_fake_response("check_dosage_adjustment", {"drug": "Metformin"}), _fake_llm_meta()),
        (_make_fake_response("classify_safety", {"classification": "safe", "reasoning": "no concerns found"}), _fake_llm_meta()),
    ]

    state = _make_diagnosed_state()
    state = run_safety_loop(state)

    assert state.phase == "complete"
    assert state.proposed_treatment == "Metformin"
    assert state.safety_classification == "safe"
    assert state.escalated is False
    assert len(state.steps_taken) == 5


@patch("src.agent.safety_loop.call_llm")
def test_safety_loop_escalates_on_severe_interaction_even_if_agent_says_safe(mock_call_llm):
    """
    I check my deterministic safety net: even if the agent's own final
    classification doesn't say escalate, a severe interaction found during
    the check should still be flagged in my failure category, since I
    never want to silently miss a severe interaction.
    """
    mock_call_llm.side_effect = [
        (_make_fake_response("propose_treatment", {"drug": "Metformin", "reasoning": "first line"}), _fake_llm_meta()),
        (_make_fake_response("get_patient_history", {}), _fake_llm_meta()),
        (_make_fake_response("check_drug_interaction", {"drug_b": "Contrast_Dye"}), _fake_llm_meta()),
        (_make_fake_response("check_dosage_adjustment", {"drug": "Metformin"}), _fake_llm_meta()),
        (_make_fake_response("classify_safety", {"classification": "safe", "reasoning": "agent missed it"}), _fake_llm_meta()),
    ]

    state = _make_diagnosed_state()
    state = run_safety_loop(state)

    assert state.failure_category == "safety_flag_severe"


@patch("src.agent.safety_loop.call_llm")
def test_safety_loop_respects_agent_escalation(mock_call_llm):
    """
    I check that when my agent explicitly classifies as escalate, my loop
    marks the state as escalated and captures the reason.
    """
    mock_call_llm.side_effect = [
        (_make_fake_response("propose_treatment", {"drug": "Metformin", "reasoning": "first line"}), _fake_llm_meta()),
        (_make_fake_response("get_patient_history", {}), _fake_llm_meta()),
        (_make_fake_response("check_drug_interaction", {"drug_b": "Contrast_Dye"}), _fake_llm_meta()),
        (_make_fake_response("check_dosage_adjustment", {"drug": "Metformin"}), _fake_llm_meta()),
        (
            _make_fake_response(
                "classify_safety",
                {"classification": "escalate", "reasoning": "severe interaction found, needs clinician review"},
            ),
            _fake_llm_meta(),
        ),
    ]

    state = _make_diagnosed_state()
    state = run_safety_loop(state)

    assert state.phase == "complete"
    assert state.safety_classification == "escalate"
    assert state.escalated is True
    assert "clinician review" in state.escalation_reason


@patch("src.agent.safety_loop.call_llm")
def test_safety_loop_stops_and_escalates_when_budget_exhausted(mock_call_llm):
    """
    I check that if my agent keeps calling tools and never reaches
    classify_safety, my loop stops once its step budget runs out rather
    than looping forever.
    """
    mock_call_llm.side_effect = [
        (_make_fake_response("get_patient_history", {}), _fake_llm_meta())
        for _ in range(10)  # more than SAFETY_STEP_BUDGET
    ]

    state = _make_diagnosed_state()
    state = run_safety_loop(state)

    assert state.phase == "escalated"
    assert state.escalated is True
    assert state.failure_category == "budget_exhausted"