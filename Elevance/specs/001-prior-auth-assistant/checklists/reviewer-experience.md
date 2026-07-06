# Reviewer Experience Quality Checklist

**Purpose**: Validate the quality and completeness of persona-specific UI, workflow, and output requirements.
**Created**: 2026-07-06

## Intake Associate Persona

- [ ] CHK001 - Is it explicitly defined what the Intake Associate can see (e.g., Intake Queue, completeness status)? [Completeness]
- [ ] CHK002 - Are the actions the Intake Associate can take (e.g., upload documents, verify demographics) clearly specified? [Clarity]
- [ ] CHK003 - Is the Intake Associate's boundary explicitly defined so they cannot access clinical gap analysis outputs? [Consistency, Gap]

## Nurse Reviewer Persona

- [ ] CHK004 - Does the spec define exactly what the Nurse Reviewer sees (e.g., Nurse Queue, Gap Checklist, Clinical Summary in Markdown)? [Completeness]
- [ ] CHK005 - Are the actions the Nurse Reviewer can take (e.g., mark checklist item status, request more info, escalate to MD) specified? [Clarity]
- [ ] CHK006 - Is the format of the evidence drill-down explicitly defined as structured data vs. natural language? [Clarity]

## Medical Director Persona

- [ ] CHK007 - Is the Medical Director's Escalation Queue view explicitly defined, including how contradictory flags are surfaced? [Coverage]
- [ ] CHK008 - Are the Medical Director's unique actions (e.g., overriding a routing decision, final clinical sign-off outside the system) clearly specified? [Clarity]

## Provider Relations Persona

- [ ] CHK009 - Is the Provider Relations queue explicitly restricted to viewing drafted missing-document requests? [Consistency]
- [ ] CHK010 - Is it explicitly stated that Provider Relations CANNOT see internal audit logs or raw clinical notes? [Consistency, Boundary]
- [ ] CHK011 - Does the spec define the format they receive the draft in (e.g., Markdown text block ready to copy-paste)? [Clarity]

## Operations Manager Persona

- [ ] CHK012 - Are the aggregate queue metrics and SLA dashboards defined for the Operations Manager? [Completeness]
- [ ] CHK013 - Is it explicitly documented whether the Operations Manager can drill down into individual patient PHI? [Boundary]

## Auditor Persona

- [ ] CHK014 - Does the spec explicitly define the Auditor's view as a structured JSON/Table timeline of `AuditLogEntry` records? [Clarity]
- [ ] CHK015 - Is it specified whether the Auditor can mutate case state or take actions, or if their view is strictly read-only? [Clarity]

## QA/Test Engineer Persona

- [ ] CHK016 - Are the boundaries for the QA persona explicitly restricted to synthetic environments only? [Boundary]
- [ ] CHK017 - Is the test scenario trigger mechanism (e.g., injecting adversarial RAG cases) defined for this persona? [Coverage]
