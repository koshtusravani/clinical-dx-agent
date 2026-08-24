"""
I implement my treatment safety ReAct loop here. This runs after my
diagnostic loop reaches a confident diagnosis. I propose a treatment, pull
the patient's history, check it for interactions and dosage concerns, and
classify the result as safe, needs_adjustment, or escalate. I never
prescribe anything myself, I only flag concerns for a clinician to review.
"""

from src.agent.prompts import SAFETY_SYSTEM_PROMPT, SAFETY_TOOLS
from src.agent.state import AgentState, StepRecord
from src.failure_taxonomy import FailureCategory, MaxRetriesExceeded, PermanentError
from src.llm_client import MODEL_REASONING, call_llm
from src.tools.base import call_tool_with_retry
from src.tools.safety_tools import (
    check_dosage_adjustment,
    check_drug_interaction,
    get_patient_history,
)
from src.agent.diagnostic_loop import _strip_markdown

# I cap the safety loop at a slightly higher step budget than a single
# diagnostic condition, since it has more mandatory sub-steps: propose,
# get history, check every existing medication, check dosage, classify.
# I calculate the safety budget dynamically based on how many medications
# a patient is actually on, since real patients can have many concurrent
# medications and my agent checks each one individually for interactions.
# A fixed budget was too small for patients with several medications.
BASE_SAFETY_STEPS = 4  # propose_treatment, get_patient_history, check_dosage_adjustment, classify_safety
SAFETY_STEP_HEADROOM = 2  # a little slack for retries or an extra look-back


def _calculate_safety_budget(num_medications: int) -> int:
    return BASE_SAFETY_STEPS + num_medications + SAFETY_STEP_HEADROOM

TOOL_FUNCTIONS = {
    "get_patient_history": get_patient_history,
    "check_drug_interaction": check_drug_interaction,
    "check_dosage_adjustment": check_dosage_adjustment,
}


def _propose_treatment(drug: str, reasoning: str) -> dict:
    """
    I package the agent's proposed treatment here. This doesn't look
    anything up, it's just a structured record of the agent's decision,
    similar to how I handle conclude_diagnosis in my diagnostic loop.
    """
    return {"drug": drug, "reasoning": reasoning}


def _classify_safety(classification: str, reasoning: str) -> dict:
    """
    I package the agent's final safety classification here. This is the
    terminal action for my safety loop.
    """
    return {"classification": classification, "reasoning": reasoning}


def _build_user_message(state: AgentState) -> str:
    lines = [f"Confirmed diagnosis: {state.final_diagnosis}."]

    if state.proposed_treatment:
        lines.append(f"Proposed treatment so far: {state.proposed_treatment}.")

    completed_actions = [s.action for s in state.steps_taken if s.status == "success"]
    if completed_actions:
        lines.append(f"Steps I've already taken: {', '.join(completed_actions)}.")

        for s in state.steps_taken:
            if s.action in ("get_patient_history", "check_drug_interaction", "check_dosage_adjustment") and s.status == "success":
                lines.append(f"- {s.action}({s.args}): {s.result}")
    else:
        lines.append("I haven't taken any steps yet. I should start by proposing a treatment.")

    lines.append("What is my next action?")
    return "\n".join(lines)


def run_safety_loop(state: AgentState) -> AgentState:
    """
    I take an AgentState that already has a confirmed diagnosis (phase set
    to treatment_safety by my diagnostic loop) and run the safety-check
    loop on it. I mutate and return the same state so both phases share one
    continuous run record.
    """
    messages = []
    step_num = len(state.steps_taken)
    patient_history = None

    # I don't know the patient's medication count until I fetch their
    # history, so I start with a conservative default budget and recompute
    # it dynamically the moment I know how many medications there are.
    steps_remaining = BASE_SAFETY_STEPS + SAFETY_STEP_HEADROOM

    while steps_remaining > 0 and state.phase == "treatment_safety":
        step_num += 1
        steps_remaining -= 1
        messages.append({"role": "user", "content": _build_user_message(state)})

        response, llm_meta = call_llm(
            messages=messages,
            model=MODEL_REASONING,
            tools=SAFETY_TOOLS,
            system=SAFETY_SYSTEM_PROMPT,
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
            state.escalation_reason = "I didn't receive a valid tool call from the model during safety checking."
            break

        action = tool_use_block.name
        args = tool_use_block.input

        try:
            if action == "propose_treatment":
                result = _propose_treatment(drug=args["drug"], reasoning=args["reasoning"])
                state.steps_taken.append(StepRecord(
                    step_num=step_num, action=action, tool_called=action,
                    args=args, result=result, reasoning=reasoning_text,
                    latency_ms=llm_meta["latency_ms"], cost_usd=llm_meta["cost_usd"],
                    retry_count=0, status="success",
                ))
                state.proposed_treatment = result["drug"]
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,
                        "content": f"Treatment proposed: {result['drug']}. Now check it against the patient's history.",
                    }],
                })

            elif action in ("get_patient_history", "check_drug_interaction", "check_dosage_adjustment"):
                tool_fn = TOOL_FUNCTIONS[action]
                call_args = dict(args)
                if action == "get_patient_history":
                    call_args["patient_id"] = state.patient_id
                if action == "check_drug_interaction" and "drug_a" not in call_args:
                    call_args["drug_a"] = state.proposed_treatment
                if action == "check_dosage_adjustment":
                    call_args["patient_factors"] = patient_history or {}

                step_logs = []
                result = call_tool_with_retry(tool_fn, call_args, on_log=step_logs.append)
                status = step_logs[-1]["status"]
                retry_count = sum(1 for l in step_logs if l["status"] == "retry")

                state.steps_taken.append(StepRecord(
                    step_num=step_num, action=action, tool_called=action,
                    args=call_args, result=result, reasoning=reasoning_text,
                    latency_ms=llm_meta["latency_ms"] + step_logs[-1]["latency_ms"],
                    cost_usd=llm_meta["cost_usd"],
                    retry_count=retry_count, status=status,
                ))

                if action == "get_patient_history":
                    patient_history = result
                    num_meds = len(result.get("medications", []))
                    recalculated_budget = _calculate_safety_budget(num_meds)
                    # I only ever expand the budget here, never shrink it, so
                    # I don't accidentally cut off a run that already has
                    # steps in progress.
                    steps_remaining = max(steps_remaining, recalculated_budget - step_num)
                
                # I flag severe interactions immediately as a safety net,
                # even if the agent doesn't classify it that way itself,
                # since missing a severe interaction is my worst possible
                # failure mode here.
                if action == "check_drug_interaction" and result.get("severity") == "severe":
                    state.failure_category = FailureCategory.SAFETY_FLAG_SEVERE

                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,
                        "content": str(result),
                    }],
                })

            elif action == "classify_safety":
                result = _classify_safety(classification=args["classification"], reasoning=args["reasoning"])
                state.steps_taken.append(StepRecord(
                    step_num=step_num, action=action, tool_called=action,
                    args=args, result=result, reasoning=reasoning_text,
                    latency_ms=llm_meta["latency_ms"], cost_usd=llm_meta["cost_usd"],
                    retry_count=0, status="success",
                ))
                state.safety_classification = result["classification"]
                state.safety_reasoning = result["reasoning"]
                state.phase = "complete"

                if result["classification"] == "escalate":
                    state.escalated = True
                    state.escalation_reason = result["reasoning"]
                break

            else:
                state.failure_category = FailureCategory.INVALID_TOOL_CALL
                state.phase = "escalated"
                state.escalated = True
                state.escalation_reason = f"I received an unknown tool name during safety checking: {action}"
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
                    "content": f"I couldn't complete that lookup: {str(e)}.",
                    "is_error": True,
                }],
            })

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
            state.escalation_reason = f"I exhausted my retries calling {e.tool_name} during safety checking."
            break

    if state.phase == "treatment_safety" and steps_remaining <= 0:
        # I ran out of safety-check steps without reaching a classification,
        # so I escalate rather than leave the treatment unclassified.
        state.phase = "escalated"
        state.escalated = True
        state.failure_category = FailureCategory.BUDGET_EXHAUSTED
        state.escalation_reason = "I used my full safety-check step budget without reaching a classification."

    return state