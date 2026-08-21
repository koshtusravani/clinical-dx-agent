"""
I wrote these tests to verify my diagnostic loop's control flow: does it
call tools correctly, does it stop when it should, does it escalate when
it should. I mock call_llm here instead of hitting the real API, since I
want these tests to run fast, free, and the same way every time.

I already verified the loop works correctly against the real Anthropic API
in my live test script. These tests check the loop's logic in isolation.
"""

from unittest.mock import MagicMock, patch

from src.agent.diagnostic_loop import run_diagnostic_loop


def _make_fake_response(tool_name: str, tool_input: dict, text: str = "My reasoning here."):
    """
    I build a fake Anthropic response object here that mimics the shape my
    loop expects: a list of content blocks with a text block and a
    tool_use block.
    """
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.input = tool_input
    tool_block.id = "fake_tool_use_id"

    response = MagicMock()
    response.content = [text_block, tool_block]
    return response


def _fake_llm_meta():
    return {
        "latency_ms": 500.0,
        "cost_usd": 0.001,
        "model": "claude-sonnet-4-6",
        "input_tokens": 100,
        "output_tokens": 50,
    }


@patch("src.agent.diagnostic_loop.call_llm")
def test_loop_orders_test_then_concludes(mock_call_llm):
    """
    I check that my loop correctly orders a test, feeds the result back,
    and then concludes when the second call decides it has enough evidence.
    This mirrors the real diabetes case I already verified live.
    """
    mock_call_llm.side_effect = [
        (
            _make_fake_response("order_test", {"test_name": "fasting_glucose", "reasoning": "checking glucose"}),
            _fake_llm_meta(),
        ),
        (
            _make_fake_response(
                "conclude_diagnosis",
                {"condition": "Type 2 Diabetes Mellitus", "confidence": 0.95, "reasoning": "glucose confirms it"},
            ),
            _fake_llm_meta(),
        ),
    ]

    state = run_diagnostic_loop(
        patient_id="test-patient-001",
        presenting_symptoms=["fatigue", "increased thirst"],
    )

    assert state.phase == "treatment_safety"
    assert state.final_diagnosis == "Type 2 Diabetes Mellitus"
    assert state.diagnosis_confidence == 0.95
    assert state.escalated is False
    assert len(state.steps_taken) == 2
    assert state.steps_taken[0].action == "order_test"
    assert state.steps_taken[1].action == "conclude_diagnosis"


@patch("src.agent.diagnostic_loop.call_llm")
def test_loop_escalates_when_agent_chooses_to(mock_call_llm):
    """
    I check that when my agent explicitly calls escalate, my loop respects
    that and stops immediately rather than continuing to loop.
    """
    mock_call_llm.side_effect = [
        (
            _make_fake_response("escalate", {"reason": "conflicting evidence, deferring to clinician"}),
            _fake_llm_meta(),
        ),
    ]

    state = run_diagnostic_loop(
        patient_id="test-patient-001",
        presenting_symptoms=["fatigue", "palpitations"],
    )

    assert state.phase == "escalated"
    assert state.escalated is True
    assert "conflicting evidence" in state.escalation_reason


@patch("src.agent.diagnostic_loop.call_llm")
def test_loop_stops_and_escalates_when_budget_exhausted(mock_call_llm):
    """
    I check that if my agent keeps ordering tests and never concludes, my
    loop stops once the step budget runs out and escalates instead of
    looping forever.
    """
    mock_call_llm.side_effect = [
        (_make_fake_response("order_test", {"test_name": "fasting_glucose", "reasoning": "step 1"}), _fake_llm_meta()),
        (_make_fake_response("order_test", {"test_name": "hba1c", "reasoning": "step 2"}), _fake_llm_meta()),
        (_make_fake_response("order_test", {"test_name": "fasting_glucose", "reasoning": "step 3"}), _fake_llm_meta()),
        (_make_fake_response("order_test", {"test_name": "hba1c", "reasoning": "step 4"}), _fake_llm_meta()),
    ]

    state = run_diagnostic_loop(
        patient_id="test-patient-001",
        presenting_symptoms=["fatigue"],
    )

    assert state.phase == "escalated"
    assert state.escalated is True
    assert state.failure_category == "budget_exhausted"
    assert state.step_budget_remaining == 0


@patch("src.agent.diagnostic_loop.call_llm")
def test_loop_handles_missing_test_and_continues(mock_call_llm):
    """
    I check that when my agent orders a test that isn't available for this
    patient, my loop catches the PermanentError, logs it correctly, and
    lets the agent try a different test on its next turn instead of
    crashing the whole run.
    """
    mock_call_llm.side_effect = [
        (_make_fake_response("order_test", {"test_name": "tsh", "reasoning": "checking thyroid"}), _fake_llm_meta()),
        (
            _make_fake_response(
                "conclude_diagnosis",
                {"condition": "Type 2 Diabetes Mellitus", "confidence": 0.8, "reasoning": "based on available data"},
            ),
            _fake_llm_meta(),
        ),
    ]

    state = run_diagnostic_loop(
        patient_id="test-patient-001",
        presenting_symptoms=["fatigue"],
    )

    assert state.steps_taken[0].status == "failed_permanent"
    assert state.failure_category == "data_unavailable"
    assert state.final_diagnosis == "Type 2 Diabetes Mellitus"