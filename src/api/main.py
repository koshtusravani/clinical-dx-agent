"""
I expose my agent through a small FastAPI layer here. This is the piece
that turns my agent from a script only I can run into something a real
client (a UI, another service, a test suite) could call over HTTP.

I keep the request and response shapes explicit with Pydantic models,
since well defined schemas are a core part of good API design, not an
afterthought.
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.agent.diagnostic_loop import run_diagnostic_loop
from src.agent.safety_loop import run_safety_loop

app = FastAPI(
    title="Clinical Dx Agent API",
    description=(
        "A clinical decision support agent API. Synthetic data only, not a medical "
        "device. Every response is a recommendation for a clinician to review, never "
        "an autonomous action."
    ),
    version="1.0.0",
)

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"


class DiagnoseRequest(BaseModel):
    patient_id: str = Field(..., description="The patient's identifier, matching a processed case file.")
    presenting_symptoms: list[str] = Field(..., description="A list of the patient's presenting symptoms.")


class StepResponse(BaseModel):
    step_num: int
    action: str
    args: dict
    result: dict | None
    status: str
    cost_usd: float
    latency_ms: float


class DiagnoseResponse(BaseModel):
    patient_id: str
    final_diagnosis: str | None
    diagnosis_confidence: float | None
    escalated: bool
    escalation_reason: str | None
    safety_classification: str | None
    total_cost_usd: float
    total_latency_ms: float
    steps: list[StepResponse]


@app.get("/health")
def health_check():
    """I use this as a simple liveness check for the API."""
    return {"status": "ok"}


@app.get("/cases/{patient_id}")
def get_case(patient_id: str):
    """
    I return the raw processed case data for a given patient, mainly
    useful for inspecting what data is available before running a
    diagnosis against it.
    """
    case_path = PROCESSED_DIR / f"{patient_id}.json"
    if not case_path.exists():
        raise HTTPException(status_code=404, detail=f"I couldn't find a processed case for patient_id {patient_id}")

    with open(case_path) as f:
        return json.load(f)


@app.post("/diagnose", response_model=DiagnoseResponse)
def diagnose(request: DiagnoseRequest):
    """
    I run my full pipeline here: the diagnostic loop, then the treatment
    safety loop if a diagnosis is reached. I return the complete outcome
    along with every step's trace, so a client can inspect exactly how I
    arrived at my recommendation.
    """
    case_path = PROCESSED_DIR / f"{request.patient_id}.json"
    if not case_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"I couldn't find a processed case for patient_id {request.patient_id}",
        )

    try:
        state = run_diagnostic_loop(
            patient_id=request.patient_id,
            presenting_symptoms=request.presenting_symptoms,
        )

        if state.phase == "treatment_safety":
            state = run_safety_loop(state)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"My pipeline failed unexpectedly: {str(e)}")

    return DiagnoseResponse(
        patient_id=state.patient_id,
        final_diagnosis=state.final_diagnosis,
        diagnosis_confidence=state.diagnosis_confidence,
        escalated=state.escalated,
        escalation_reason=state.escalation_reason,
        safety_classification=state.safety_classification,
        total_cost_usd=state.total_cost_usd(),
        total_latency_ms=state.total_latency_ms(),
        steps=[
            StepResponse(
                step_num=s.step_num,
                action=s.action,
                args=s.args,
                result=s.result,
                status=s.status,
                cost_usd=s.cost_usd,
                latency_ms=s.latency_ms,
            )
            for s in state.steps_taken
        ],
    )