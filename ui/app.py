"""
I built this Gradio app as the live demo for my clinical decision support
agent. A user enters a patient case, and I stream the agent's reasoning
step by step: which test it orders, what it finds, how it adapts, and
finally its safety check on the proposed treatment.

Every run here makes real calls to the Anthropic API and costs real money,
so I show a cost estimate and require an explicit confirmation before
running.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gradio as gr

from src.agent.diagnostic_loop import run_diagnostic_loop
from src.agent.safety_loop import run_safety_loop

EXAMPLE_CASES = [
    {
        "label": "Diabetes (classic triad, 2-step confirmatory workup)",
        "patient_id": "test-patient-001",
        "symptoms": "fatigue, increased thirst, frequent urination",
    },
    {
        "label": "UTI with complex medication history (polypharmacy safety catch)",
        "patient_id": "0c2b0c70-00de-0c79-9130-074552700431",
        "symptoms": "burning with urination, urinary frequency, pelvic discomfort",
    },
]


def _format_step(step_num: int, action: str, args: dict, result, status: str) -> str:
    """
    I format one step of the agent's trace as a readable markdown block for
    the live display.
    """
    icon = {"success": "✅", "failed_permanent": "⚠️", "failed_exhausted_retries": "❌"}.get(status, "•")

    lines = [f"### Step {step_num}: `{action}` {icon}"]

    if action == "order_test":
        lines.append(f"**Ordering:** {args.get('test_name')}")
        lines.append(f"**Reasoning:** {args.get('reasoning')}")
        if result:
            lines.append(f"**Result:** {result}")
    elif action == "conclude_diagnosis":
        lines.append(f"**Diagnosis:** {args.get('condition')} (confidence: {args.get('confidence')})")
        lines.append(f"**Reasoning:** {args.get('reasoning')}")
    elif action == "escalate":
        lines.append(f"**Escalating.** Reason: {args.get('reason')}")
    elif action == "propose_treatment":
        lines.append(f"**Proposed treatment:** {args.get('drug')}")
        lines.append(f"**Reasoning:** {args.get('reasoning')}")
    elif action == "get_patient_history":
        lines.append(f"**Patient history:** {result}")
    elif action == "check_drug_interaction":
        lines.append(f"**Checking:** {args.get('drug_a')} + {args.get('drug_b')}")
        if result:
            lines.append(f"**Result:** {result.get('severity')} — {result.get('description')}")
    elif action == "check_dosage_adjustment":
        if result:
            lines.append(f"**Dosage check:** {result.get('recommendation')}")
    elif action == "classify_safety":
        lines.append(f"**Final classification:** {args.get('classification')}")
        lines.append(f"**Reasoning:** {args.get('reasoning')}")

    return "\n\n".join(lines) + "\n\n---\n"


def run_case(patient_id: str, symptoms_text: str, confirmed: bool):
    """
    I run the full pipeline and yield markdown updates after each step, so
    the UI streams progress live instead of waiting for the whole run to
    finish before showing anything.
    """
    if not confirmed:
        yield "Please check the cost confirmation box before running. Every run makes real, billed API calls."
        return

    if not patient_id.strip():
        yield "Please enter a patient ID."
        return

    symptoms = [s.strip() for s in symptoms_text.split(",") if s.strip()]
    if not symptoms:
        yield "Please enter at least one presenting symptom, comma separated."
        return

    output = f"## Running case for patient `{patient_id}`\n\n**Presenting symptoms:** {', '.join(symptoms)}\n\n---\n\n"
    yield output

    try:
        state = run_diagnostic_loop(patient_id=patient_id, presenting_symptoms=symptoms)
    except Exception as e:
        yield output + f"\n\n**Run failed:** {e}"
        return

    output += "## Diagnostic phase\n\n"
    for s in state.steps_taken:
        output += _format_step(s.step_num, s.action, s.args, s.result, s.status)
        yield output

    if state.phase == "treatment_safety":
        output += "\n## Treatment safety phase\n\n"
        yield output

        diagnostic_step_count = len(state.steps_taken)
        state = run_safety_loop(state)

        for s in state.steps_taken[diagnostic_step_count:]:
            output += _format_step(s.step_num, s.action, s.args, s.result, s.status)
            yield output

    output += "\n## Summary\n\n"
    output += f"- **Final diagnosis:** {state.final_diagnosis or 'None reached'}\n"
    output += f"- **Escalated:** {state.escalated}\n"
    if state.escalated:
        output += f"- **Escalation reason:** {state.escalation_reason}\n"
    if state.safety_classification:
        output += f"- **Safety classification:** {state.safety_classification}\n"
    output += f"- **Total cost:** ${state.total_cost_usd():.4f}\n"
    output += f"- **Total latency:** {state.total_latency_ms():.0f} ms\n"

    yield output


def load_example(example_label: str):
    for ex in EXAMPLE_CASES:
        if ex["label"] == example_label:
            return ex["patient_id"], ex["symptoms"]
    return "", ""


with gr.Blocks(title="Clinical Dx Agent") as demo:
    gr.Markdown(
        "# Clinical Dx Agent\n"
        "A synthetic data clinical decision support demo. Enter a patient ID and presenting symptoms, "
        "then watch the agent work through diagnosis and treatment safety checking, one step at a time.\n\n"
        "**This is a research and engineering demo using synthetic Synthea patient data. "
        "It is not a medical device and makes no clinical claims.**"
    )

    with gr.Row():
        with gr.Column(scale=1):
            example_dropdown = gr.Dropdown(
                choices=[ex["label"] for ex in EXAMPLE_CASES],
                label="Load an example case",
            )
            patient_id_input = gr.Textbox(label="Patient ID", placeholder="e.g. test-patient-001")
            symptoms_input = gr.Textbox(
                label="Presenting symptoms (comma separated)",
                placeholder="e.g. fatigue, increased thirst, frequent urination",
            )
            cost_confirm = gr.Checkbox(
                label="I understand this run makes real, billed API calls (typically $0.02-0.30 per case)"
            )
            run_button = gr.Button("Run case", variant="primary")

        with gr.Column(scale=2):
            output_display = gr.Markdown(label="Agent trace")

    example_dropdown.change(fn=load_example, inputs=example_dropdown, outputs=[patient_id_input, symptoms_input])
    run_button.click(fn=run_case, inputs=[patient_id_input, symptoms_input, cost_confirm], outputs=output_display)


if __name__ == "__main__":
    demo.launch()
    