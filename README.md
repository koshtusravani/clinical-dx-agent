# Clinical Dx Agent

A clinical decision support agent that works through a diagnostic workup one step at a time, then checks its proposed treatment against a patient's history before flagging anything a clinician should review. Built as an AI engineering portfolio project to demonstrate multi step agent orchestration, tool use, retry and failure handling, and rigorous evaluation, not as a deployable medical product.

**This is a synthetic data research and engineering demo. It is not a medical device, it does not diagnose real patients, and it should never be used for real clinical decisions.**

## What it does

A clinician (simulated in this project) enters a patient's presenting symptoms. The agent recommends one diagnostic test at a time, reasons over the result, and adapts its next recommendation based on what it learns, exactly like a real workup rather than a single batch of orders. Once it reaches a confident diagnosis, it proposes a first line treatment and checks that treatment against the patient's existing medications and conditions for interactions and dosage concerns. At every step, if the evidence is weak, conflicting, or the treatment carries real risk, it escalates to a clinician instead of guessing.

Everything the agent decides is a recommendation. It never acts autonomously and never bypasses a human.

## Example run

Patient presents with fatigue, increased thirst, and frequent urination.

1. Agent orders fasting glucose. Result: 182 mg/dL, above the diabetic threshold.
2. Agent recognizes one elevated reading isn't fully diagnostic and orders HbA1c to confirm. Result: 8.1%, also elevated.
3. Two independent, concordant results are enough. Agent concludes Type 2 Diabetes Mellitus at 0.95 confidence.
4. Agent proposes metformin as first line treatment.
5. Agent pulls the patient's history and finds a documented history of reduced kidney function.
6. Agent classifies the treatment as escalate, since metformin carries real risk in patients with renal impairment, rather than approving it outright.

A second example, drawn directly from this project's eval run: a patient with a confirmed urinary tract infection and 9 concurrent medications, including an existing course of the same antibiotic being proposed. The agent's safety check caught the duplicate prescription risk, a documented pregnancy that contraindicates the drug, and several medications it had no interaction data for, and escalated rather than approve the treatment. Full trace in `data/gold_sets` (generated locally, not committed, see Reproducing this eval below).

## Architecture

Two connected ReAct style loops sharing one continuous state object, not a single long prompt.

**Diagnostic loop.** Given presenting symptoms, the agent picks one action per turn: order a test, conclude a diagnosis, or escalate. Every test result feeds back into the next decision, so the agent's plan changes based on what it actually finds, not a fixed checklist decided up front. A per condition step budget (calibrated to how many confirmatory tests a real workup for that condition typically needs) caps how long the agent can keep testing before it must either conclude or escalate.

**Treatment safety loop.** Runs after a diagnosis is reached. The agent proposes a first line treatment, pulls the patient's history, checks the proposed drug against every existing medication for interactions, checks for dosage adjustments based on patient factors, and classifies the result as safe, needs adjustment, or escalate. A deterministic safety net in the code, not just the model's own judgment, flags any interaction the check returns as severe, so a missed severe interaction can never silently pass as safe.

**Tool use.** Every tool call goes through a single retry wrapper with a closed failure taxonomy: transient errors retry with backoff, missing data prompts the agent to pick a different next step, and exhausted retries or an invalid tool call trigger escalation. `disable_parallel_tool_use` keeps the agent making exactly one decision per turn, matching the sequential structure of a real workup.

**Models.** Claude Sonnet handles the reasoning heavy steps (differential diagnosis, treatment proposal). Claude Haiku is available for cheap structured sub tasks. This tiered routing is a deliberate cost and quality tradeoff, not an afterthought.

## Data

Built entirely on data generated locally with [Synthea](https://github.com/synthetichealth/synthea), an open source synthetic patient generator. No real patient data was used anywhere in this project. I generated 3,402 synthetic Massachusetts patients, flattened their FHIR records into a simplified case schema, and built a balanced eval gold set of 100 cases (20 per condition) across 5 target conditions: Type 2 Diabetes Mellitus, Anemia, Hypertension, Urinary Tract Infection, and Hyperlipidemia.

Hypothyroidism was in my original scope but dropped after generating a large population confirmed it's rare in Synthea's disease model (3 usable cases out of 3,402 patients). I chose to keep 5 well populated conditions rather than force a 6th backed by too little data to report a meaningful number on.

## Eval results

100 case run, 20 cases per condition, fixed random seed for reproducibility.

| Condition | Correct | Incorrect | Escalated (no diagnosis) | Avg steps | Avg cost | Avg latency |
|---|---|---|---|---|---|---|
| Type 2 Diabetes Mellitus | 35% | 0% | 65% | 3.2 | $0.14 | 28.3s |
| Urinary Tract Infection | 95% | 0% | 5% | 2.0 | $0.34 | 54.2s |
| Anemia | 20% | 5% | 75% | 2.65 | $0.09 | 24.9s |
| Hyperlipidemia | 25% | 50% | 25% | 3.1 | $0.15 | 34.9s |
| Hypertension | 0% | 55% | 45% | 3.25 | $0.25 | 40.3s |
| **Overall** | **35%** | **22%** | **43%** | | **$0.19** | **36.5s** |

An additional 33% of all cases (across every condition) reached a **correct** diagnosis and then had their **proposed treatment** escalated during safety checking, for reasons like undocumented medication interactions or contraindicated conditions. That escalation is a distinct, later judgment about treatment safety, not a diagnostic failure, and it's tracked separately in the raw report.

**Reading these numbers honestly, not just reporting them:**

- **UTI's 95% accuracy** reflects that it has the most distinctive presenting symptoms and a two test confirmatory workup (leukocyte esterase, nitrite) that maps cleanly to real data.
- **Diabetes never produced a wrong diagnosis.** It either reached the correct answer or escalated. Zero false positives on the most common condition in this eval is a meaningful safety property, even though the escalation rate looks high at first glance.
- **Hypertension and Hyperlipidemia show real, higher error rates**, and I traced this to a specific, explainable cause: both conditions are often asymptomatic or found incidentally in real practice, unlike diabetes or UTI which have a distinctive symptom triad. My synthetic symptom mapping for these two conditions (headache and occasional dizziness for hypertension, for example) is necessarily far less specific, which makes the diagnostic task genuinely harder, not a sign the agent is broken. A stretch improvement would be framing these as incidental findings on routine screening rather than symptom driven presentations.
- **`data_unavailable` and `budget_exhausted` account for 43 of the 100 cases.** This mostly reflects Synthea patients missing a specific lab the agent wanted, or the agent using its full step budget without converging, both of which trigger an honest escalation rather than a guess. This is the agent's core design principle (never diagnose without confident, consistent evidence) working as intended against real, messy data.
- **Cost varies significantly by condition**, driven almost entirely by how many medications a patient is on. The safety loop checks every existing medication individually for interactions, so a patient on 9 medications costs meaningfully more to fully safety check than one on a single medication. This is a known, real tradeoff, and a batched interaction check (checking several medications in one tool call) is a natural next optimization.

Full per-case traces and the raw eval report are generated locally and are not committed to this repo (see Reproducing this eval below), since they're derived data, not source.

## Cost and latency

Average $0.19 and 36.5 seconds per full case (diagnosis plus safety check) across the 100 case eval, using Claude Sonnet for all reasoning steps in this run. The full 100 case eval cost $19.19 total. Cost per case ranges from under $0.02 for a quick 2 step diagnosis with a single medication safety check, up to $0.80+ for a patient with many concurrent medications and an extended, multi step differential.

## Stack

Python, Anthropic Claude API (native tool use, no agent framework), FastAPI (planned for the demo API layer), Gradio (planned for the live demo UI), Synthea for synthetic patient generation, SQLite for run logging (planned).

I chose not to use LangChain or a similar framework. Hand rolling the loop, retry logic, and state machine keeps the internals fully visible and was a deliberate choice to demonstrate understanding of agent mechanics directly, not just framework usage.

## Reproducing this eval

```bash
# Generate synthetic patients (requires Java 17+)
git clone https://github.com/synthetichealth/synthea.git
cd synthea && ./run_synthea.bat -p 2500 Massachusetts

# Copy output into this project, then flatten and build the gold set
python src/data_pipeline/flatten_case.py
python src/eval/gold_set_builder.py

# Run the eval and build the report
python src/eval/run_diagnostic_eval.py
python src/eval/report_builder.py
```

## Governance and safety framing

Since this project handles a health adjacent domain even with synthetic data, I designed it with the constraints a real deployment would face in mind, though I did not implement them, since that would be out of scope for a portfolio project using synthetic data only.

**What a real deployment would require that this project intentionally does not implement:** HIPAA aligned technical safeguards (encryption at rest and in transit, audit logging tied to real user identities, business associate agreements), a formal validation and monitoring process aligned with FDA guidance on AI and ML based Software as a Medical Device, and algorithm transparency documentation in line with ONC and NIST AI Risk Management Framework guidance (documented limitations, known failure modes, and performance monitoring over time).

**What this project does implement as a demonstration of that awareness:** a closed failure taxonomy with every non success outcome bucketed and logged, a three way outcome classification in the eval report (correct, incorrect, escalated) rather than a single misleading accuracy number, a deterministic safety net for severe drug interactions that doesn't rely solely on the model's own judgment, and an explicit, honest limitations section in this README rather than an inflated accuracy claim.

A lightweight governance module (access control, audit logging, data minimization) is planned as a stretch feature, built as a clearly separated addition once the core agent and eval are proven, not mixed into the core engineering.

## Limitations

- Presenting symptoms for the eval are hand mapped per condition, not drawn from real patient chief complaints, since Synthea's data doesn't include a symptom field. This makes asymptomatic conditions (hypertension, hyperlipidemia) harder to diagnose from symptoms alone, as discussed above.
- The drug interaction and dosage checker uses a small, hand curated local table rather than a live pharmacological database, so many real medications return "unknown" rather than a definitive answer. This is intentional for eval reproducibility, and a real deployment would need a maintained clinical data source.
- Safety check cost scales with how many medications a patient is on, since each is checked individually. A batched check is a natural optimization not yet built.
- This project has not been reviewed by a clinician and makes no claim to clinical accuracy beyond what's shown in the eval report above.

## Stretch features (not yet built)

Expanding condition coverage beyond the current 5, multi drug regimen checking, confidence calibration reporting, a Hugging Face open weight model comparison against Claude on the same eval set, an adversarial test suite for escalation logic, a batch eval dashboard UI, and the governance module described above.