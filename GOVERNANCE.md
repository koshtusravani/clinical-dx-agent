# Governance and Safety Framing

This document describes how Clinical Dx Agent was designed with real world clinical AI governance constraints in mind, even though it operates entirely on synthetic data and implements only a subset of what a real deployment would require. It exists to make explicit what would be needed for real deployment, and to draw a clear line between that and what this project actually is: a portfolio engineering demonstration.

**This project is not, and does not claim to be, a medical device, a HIPAA covered system, or a tool validated for real clinical use.**

## Why this matters for a synthetic data project

Health adjacent AI systems carry real risk even in a research or educational context, because the patterns of reasoning, escalation, and safety checking demonstrated here are the same patterns a real system would need. Building this project with governance constraints in mind from the start, rather than treating them as an afterthought, is itself part of the engineering discipline this project is meant to demonstrate.

## Relevant frameworks

**HIPAA (Health Insurance Portability and Accountability Act).** Governs real Protected Health Information (PHI) handled by covered entities and their business associates. This project uses no real PHI at any point, since all patient data is generated synthetically by Synthea. HIPAA does not technically apply, but its Security Rule and Privacy Rule provide the right vocabulary for what real deployment would require: encryption at rest and in transit, access controls, audit logging, minimum necessary use, and business associate agreements with any third party handling patient data.

**FDA guidance on AI and ML based Software as a Medical Device (SaMD).** The agent's diagnostic and treatment safety recommendations are exactly the kind of function the FDA's SaMD framework addresses: how AI driven clinical decision support should be validated, monitored for performance drift, and labeled with a clear statement of intended use and limitations. This project does not seek or claim any such clearance. It borrows the framework's vocabulary (intended use, known limitations, performance monitoring) to describe itself honestly.

**ONC (Office of the National Coordinator) transparency requirements and the NIST AI Risk Management Framework.** Both push toward documented algorithm transparency: known limitations, failure modes, and performance characteristics disclosed rather than implied. This project's eval report and the Limitations section in the README are a direct response to that expectation, even though nothing here is certified health IT.

## What real deployment would require that this project does not implement

- **Technical safeguards.** Encryption of patient data at rest and in transit, role based access control tied to real, authenticated user identities, and audit logging of every access to a patient record, not just every agent decision.
- **Legal and organizational controls.** Business associate agreements with any vendor or API provider touching real PHI, a documented data retention and deletion policy, and a formal incident response plan.
- **Clinical validation.** Review by a licensed clinician of the agent's diagnostic and safety reasoning across a much larger and more representative case set than 100 synthetic patients, ideally with real world outcome data, before any claim of clinical usefulness could be made.
- **Ongoing monitoring.** Performance and failure rate monitoring over time in production, since a model or prompt change could silently shift the escalation rate or accuracy shown in this project's one time eval snapshot.
- **Bias and fairness auditing.** No analysis has been done on whether this agent's accuracy or escalation behavior differs systematically across patient demographics. Synthea's synthetic population is not necessarily representative, and this project makes no claim that its results would generalize.

## What this project does implement as a demonstration of governance aware engineering

- **A closed failure taxonomy.** Every non success outcome is bucketed into one of six named categories (`transient_tool_error`, `data_unavailable`, `invalid_tool_call`, `reasoning_failure`, `budget_exhausted`, `safety_flag_severe`), logged, and reportable, rather than handled with an unstructured catch all.
- **A three way outcome classification in the eval report.** Correct, incorrect, and escalated are tracked and reported separately, rather than collapsed into a single accuracy number that would misrepresent a deliberately conservative agent as a poorly performing one.
- **A deterministic safety net for severe drug interactions**, implemented in code rather than left entirely to the model's own judgment, so a severe interaction cannot silently pass as safe even if the model's own classification misses it.
- **An explicit, honest limitations section**, including specific, traced explanations for where and why the agent performs worse on certain conditions, rather than an inflated or vague accuracy claim.
- **No autonomous action.** At every phase, the agent's output is a recommendation logged for a clinician to review. It never independently orders a real test, prescribes a real medication, or takes any action outside its own synthetic case data.

## Planned, not yet built

A lightweight governance module: request level access control, structured audit logging of every case access (not just agent decisions), and a data minimization pass that strips or hashes any direct patient identifiers before they enter the LLM context. This is scoped as a stretch feature, to be built as a clearly separated module once the core agent and eval harness are proven solid, rather than mixed into the core engineering work.