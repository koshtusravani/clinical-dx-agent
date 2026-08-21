"""
I use this shared state object to track everything happening across one run
of the agent loop. I made it an explicit dataclass instead of hiding state in
prompt text, so every step is inspectable and I can grade it in the eval
harness later.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional


Phase = Literal["diagnosing", "treatment_safety", "escalated", "complete"]


@dataclass
class DifferentialEntry:
    condition: str
    confidence: float  # my agent's own stated confidence, 0.0 to 1.0
    reasoning: str


@dataclass
class StepRecord:
    step_num: int
    action: str  # for example "order_test", "conclude_diagnosis", "escalate"
    tool_called: Optional[str]
    args: dict
    result: Optional[dict]
    reasoning: str
    latency_ms: float
    cost_usd: float
    retry_count: int
    status: str  # "success", "retry", "failed_permanent", or "failed_exhausted_retries"


@dataclass
class AgentState:
    run_id: str
    patient_id: str
    presenting_symptoms: list[str]

    steps_taken: list[StepRecord] = field(default_factory=list)
    current_differential: list[DifferentialEntry] = field(default_factory=list)

    step_budget_remaining: int = 4
    phase: Phase = "diagnosing"

    final_diagnosis: Optional[str] = None
    diagnosis_confidence: Optional[float] = None

    proposed_treatment: Optional[str] = None
    safety_classification: Optional[Literal["safe", "needs_adjustment", "escalate"]] = None
    safety_reasoning: Optional[str] = None

    escalated: bool = False
    escalation_reason: Optional[str] = None
    failure_category: Optional[str] = None

    def total_cost_usd(self) -> float:
        return sum(s.cost_usd for s in self.steps_taken)

    def total_latency_ms(self) -> float:
        return sum(s.latency_ms for s in self.steps_taken)

    def steps_to_diagnosis(self) -> int:
        return len([s for s in self.steps_taken if s.action == "order_test"])