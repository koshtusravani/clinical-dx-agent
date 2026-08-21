"""
I use this script to manually run my diagnostic loop against a real patient
case and watch the reasoning happen step by step. This is not an automated
test, since it costs real API calls and its output can vary between runs.
I use it to sanity check the loop is wired correctly before trusting it in
my eval harness.
"""

import sys
from pathlib import Path

# I add the project root to sys.path here since conftest.py only applies
# when pytest runs, not for a plain python script invocation like this one.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.diagnostic_loop import run_diagnostic_loop

if __name__ == "__main__":
    state = run_diagnostic_loop(
        patient_id="test-patient-001",
        presenting_symptoms=["fatigue", "increased thirst", "frequent urination"],
    )

    print("\n--- Run summary ---")
    print(f"Patient: {state.patient_id}")
    print(f"Phase reached: {state.phase}")
    print(f"Final diagnosis: {state.final_diagnosis}")
    print(f"Confidence: {state.diagnosis_confidence}")
    print(f"Escalated: {state.escalated}")
    if state.escalated:
        print(f"Escalation reason: {state.escalation_reason}")
    print(f"Total cost: ${state.total_cost_usd():.4f}")
    print(f"Total latency: {state.total_latency_ms():.1f} ms")

    print("\n--- Step by step trace ---")
    for s in state.steps_taken:
        print(f"Step {s.step_num}: {s.action} -> status={s.status}")
        print(f"  reasoning: {s.reasoning[:200]}")
        print(f"  args: {s.args}")
        print(f"  result: {s.result}")