"""
I use this script to manually run my full pipeline against a real patient
case and watch the reasoning happen step by step, from diagnosis through
treatment safety checking. This is not an automated test, since it costs
real API calls and its output can vary between runs. I use it to sanity
check both loops are wired correctly together before trusting them in my
eval harness.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.diagnostic_loop import run_diagnostic_loop
from src.agent.safety_loop import run_safety_loop

if __name__ == "__main__":
    state = run_diagnostic_loop(
        patient_id="test-patient-001",
        presenting_symptoms=["fatigue", "increased thirst", "frequent urination"],
    )

    print("\n=== DIAGNOSTIC PHASE ===")
    print(f"Phase reached: {state.phase}")
    print(f"Final diagnosis: {state.final_diagnosis}")
    print(f"Confidence: {state.diagnosis_confidence}")
    print(f"Escalated: {state.escalated}")

    if state.phase == "treatment_safety":
        state = run_safety_loop(state)

        print("\n=== TREATMENT SAFETY PHASE ===")
        print(f"Phase reached: {state.phase}")
        print(f"Proposed treatment: {state.proposed_treatment}")
        print(f"Safety classification: {state.safety_classification}")
        print(f"Escalated: {state.escalated}")
        if state.escalated:
            print(f"Escalation reason: {state.escalation_reason}")

    print("\n=== RUN SUMMARY ===")
    print(f"Total cost: ${state.total_cost_usd():.4f}")
    print(f"Total latency: {state.total_latency_ms():.1f} ms")
    print(f"Failure category: {state.failure_category}")

    print("\n=== FULL STEP BY STEP TRACE ===")
    for s in state.steps_taken:
        print(f"Step {s.step_num}: {s.action} -> status={s.status}")
        print(f"  reasoning: {s.reasoning[:200]}")
        print(f"  args: {s.args}")
        print(f"  result: {s.result}")
        print()