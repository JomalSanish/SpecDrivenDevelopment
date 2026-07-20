# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]

**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]

**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]

**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]

**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]

**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]

**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]

**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]

**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Answer each gate for this feature. Mark ✅ Pass, ❌ Fail (justify below), or N/A.

| # | Principle | Gate Question | Status |
|---|-----------|---------------|--------|
| I | On-Premises Inference Only | Does this feature introduce any call to an external AI/ML or storage API? | |
| II | Human-Only Clinical Routing | Does this feature add any automated approve/deny path, or introduce a `human_review_required` boolean? | |
| III | Auth & Authz Everywhere | Does every new route carry JWT validation AND an explicit role check? | |
| IV | LLM Sizing & Reliability | If LLM is used, is the model ≤ 4 B params (phi4-mini or llama3.2:3b) with JSON-structured output? | |
| V | Hybrid Document Extraction | Does text extraction attempt native PDF (PyMuPDF) first, OCR (EasyOCR) only on near-empty pages, with chunk-level provenance metadata? | |
| VI | Best-Effort Field Extraction | Does the LLM leave unconfident fields blank rather than guessing? | |
| VII | Confidence Bands | Are confidence displays limited to the three bands (Present ≥85%, Unclear 70–85%, Absent <70%)? | |
| VIII | Hybrid Retrieval | Does retrieval apply exact/keyword for identifiers and dense semantic for narrative, with RRF + keyword-miss cap? | |
| IX | Policy Management | Is policy upload restricted to admin? Does the UI support full manual add/edit/delete before save? | |
| X | Case Editing & Audit Trail | Does admin-edit of a decided case require a comment, re-queue it, and preserve the original decision in the audit log? | |
| XI | Nurse Case Locking | Does opening a case acquire an exclusive lock with a 30-min inactivity auto-release? | |
| XII | Infrastructure Ceiling | Does this feature require more than 2 Docker containers, or attempt to run GPU workloads inside Docker/WSL2? | |
| XIII | Secrets Abstraction | Are all secrets accessed through the secrets-abstraction module (no raw `os.environ` calls)? | |
| XIV | Schema Change Discipline | Are all schema changes shipped as new Alembic migrations (no edits to applied migrations)? | |

> **Complexity Justification (if any gate fails)**: Fill the Complexity Tracking section below.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
