"""
I implement my diagnostic ReAct loop here. On each iteration I call Claude
with the conversation so far, read which tool it wants to call next,
execute that tool through my retry wrapper, and feed the result back in.
I keep looping until my agent concludes a diagnosis, escalates, or runs out
of its step budget, whichever comes first.
"""

import json

from src.agent.prompts import DIAGNOSTIC_SYSTEM_PROMPT, DIAGNOSTIC_TOOLS
from src.agent.state import AgentState, DifferentialEntry, StepRecord
from src.failure_taxonomy import FailureCategory, MaxRetriesExceeded, PermanentError
from src.llm_client import MODEL_REASONING, call_llm
from src.logging_utils import new_run_id
from src.tools.base import call_tool_with_retry
from src.tools.diagnostic_tools import conclude_diagnosis, escalate, order_test

import re


def _strip_markdown(text: str) -> str:
    """
    I strip common markdown artifacts from reasoning text as a safety net,
    in case the model doesn't perfectly follow my plain text instruction.
    """
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)      # italics
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)  # headers
    text = re.sub(r"^[-•]\s*", "", text, flags=re.MULTILINE)  # bullet points
    return text.strip()

TOOL_FUNCTIONS = {
    "order_test": order_test,
    "conclude_diagnosis": conclude_diagnosis,
    "escalate": escalate,
}


def _build_user_message(state: AgentState) -> str:
    lines = [f"Presenting symptoms: {', '.join(state.presenting_symptoms)}."]

    test_steps = [s for s in state.steps_taken if s.action == "order_test" and s.status == "success"]
    if test_steps:
        lines.append("Test results so far:")
        for s in test_steps:
            lines.append(f"- {s.args.get('test_name')}: {s.result}")
    else:
        lines.append("No tests have been ordered yet.")

    lines.append(f"I have {state.step_budget_remaining} diagnostic steps remaining. What is my next action?")
    return "\n".join(lines)


def run_diagnostic_loop(patient_id: str, presenting_symptoms: list[str]) -> AgentState:
    state = AgentState(
        run_id=new_run_id(),
        patient_id=patient_id,
        presenting_symptoms=presenting_symptoms,
    )

    messages = []
    step_num = 0

    while state.step_budget_remaining > 0 and state.phase == "diagnosing":
        step_num += 1
        messages.append({"role": "user", "content": _build_user_message(state)})

        response, llm_meta = call_llm(
            messages=messages,
            model=MODEL_REASONING,
            tools=DIAGNOSTIC_TOOLS,
            system=DIAGNOSTIC_SYSTEM_PROMPT,
            tool_choice={"type": "any", "disable_parallel_tool_use": True},
        )

        messages.append({"role": "assistant", "content": response.content})

        tool_use_block = next((b for b in response.content if b.type == "tool_use"), None)
        text_block = next((b for b in response.content if b.type == "text"), None)
        reasoning_text = _strip_markdown(text_block.text) if text_block else ""

        if tool_use_block is None:
            state.failure_category = FailureCategory.INVALID_TOOL_CALL
            state.phase = "escalated"
            state.escalated = True
            state.escalation_reason = "I didn't receive a valid tool call from the model."
            break

        action = tool_use_block.name
        args = tool_use_block.input
        tool_fn = TOOL_FUNCTIONS.get(action)

        if tool_fn is None:
            state.failure_category = FailureCategory.INVALID_TOOL_CALL
            state.phase = "escalated"
            state.escalated = True
            state.escalation_reason = f"I received an unknown tool name: {action}"
            break

        step_logs = []
        try:
            if action == "order_test":
                result = call_tool_with_retry(
                    tool_fn,
                    {"patient_id": patient_id, "test_name": args["test_name"]},
                    on_log=step_logs.append,
                )
                status = step_logs[-1]["status"]
                retry_count = sum(1 for l in step_logs if l["status"] == "retry")

                state.steps_taken.append(StepRecord(
                    step_num=step_num, action=action, tool_called=action,
                    args=args, result=result, reasoning=reasoning_text,
                    latency_ms=llm_meta["latency_ms"] + step_logs[-1]["latency_ms"],
                    cost_usd=llm_meta["cost_usd"],
                    retry_count=retry_count, status=status,
                ))

                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,
                        "content": json.dumps(result),
                    }],
                })

                state.step_budget_remaining -= 1

            elif action == "conclude_diagnosis":
                result = tool_fn(
                    condition=args["condition"],
                    confidence=args["confidence"],
                    reasoning=args["reasoning"],
                )
                state.steps_taken.append(StepRecord(
                    step_num=step_num, action=action, tool_called=action,
                    args=args, result=result, reasoning=reasoning_text,
                    latency_ms=llm_meta["latency_ms"], cost_usd=llm_meta["cost_usd"],
                    retry_count=0, status="success",
                ))
                state.final_diagnosis = result["condition"]
                state.diagnosis_confidence = result["confidence"]
                state.current_differential.append(DifferentialEntry(
                    condition=result["condition"],
                    confidence=result["confidence"],
                    reasoning=result["reasoning"],
                ))
                state.phase = "treatment_safety"
                break

            elif action == "escalate":
                result = tool_fn(reason=args["reason"])
                state.steps_taken.append(StepRecord(
                    step_num=step_num, action=action, tool_called=action,
                    args=args, result=result, reasoning=reasoning_text,
                    latency_ms=llm_meta["latency_ms"], cost_usd=llm_meta["cost_usd"],
                    retry_count=0, status="success",
                ))
                state.escalated = True
                state.escalation_reason = result["reason"]
                state.phase = "escalated"
                break

        except PermanentError as e:
            state.steps_taken.append(StepRecord(
                step_num=step_num, action=action, tool_called=action,
                args=args, result=None, reasoning=reasoning_text,
                latency_ms=llm_meta["latency_ms"], cost_usd=llm_meta["cost_usd"],
                retry_count=0, status="failed_permanent",
            ))
            state.failure_category = FailureCategory.DATA_UNAVAILABLE
            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use_block.id,
                    "content": f"That test isn't available for this patient: {str(e)}. Please pick a different test.",
                    "is_error": True,
                }],
            })
            state.step_budget_remaining -= 1

        except MaxRetriesExceeded as e:
            state.steps_taken.append(StepRecord(
                step_num=step_num, action=action, tool_called=action,
                args=args, result=None, reasoning=reasoning_text,
                latency_ms=llm_meta["latency_ms"], cost_usd=llm_meta["cost_usd"],
                retry_count=2, status="failed_exhausted_retries",
            ))
            state.failure_category = FailureCategory.TRANSIENT_TOOL_ERROR
            state.phase = "escalated"
            state.escalated = True
            state.escalation_reason = f"I exhausted my retries calling {e.tool_name}."
            break

    if state.phase == "diagnosing" and state.step_budget_remaining <= 0:
        state.phase = "escalated"
        state.escalated = True
        state.failure_category = FailureCategory.BUDGET_EXHAUSTED
        state.escalation_reason = "I used my full diagnostic step budget without reaching a confident diagnosis."

    return state