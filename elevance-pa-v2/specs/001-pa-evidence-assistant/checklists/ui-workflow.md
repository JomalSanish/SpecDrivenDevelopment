# UI / Workflow Requirements Checklist

**Feature**: `001-pa-evidence-assistant`
**Created**: 2026-07-20
**Checklist Type**: UI & Workflow — Requirements Quality Validation
**Purpose**: Validate that UI interaction, role-gating, workflow state transition, accessibility, and edge-case requirements are complete, unambiguous, consistent, and measurable before implementation begins. These items test whether the *requirements are well-written*, not whether the implementation behaves correctly.
**Source documents**: spec.md (US1–US5, FR-014–017, FR-030–038, FR-040–045, FR-050–055, Edge Cases, SC-005–008), data-model.md (Case state machine), contracts/nurse-review.md, contracts/policies.md, contracts/admin.md, plan.md §Project Structure

---

## Requirement Completeness — Sidebar & Role-Gating

- [ ] CHK001 - Does the spec define which sidebar items are visible to each role (intake, nurse, admin) — or only which areas they can *access*? Visibility (showing vs. hiding a menu item) and access-control (returning 403) are distinct requirements; is each defined separately? [Completeness, Gap, Spec §FR-004]
- [ ] CHK002 - Is a requirement specified for the behavior of a direct URL navigation attempt to a role-restricted page (e.g., an intake associate navigating directly to `/admin`) — should the UI redirect to the login page, show a "not authorized" message, or silently redirect to the user's home area? [Completeness, Gap, Spec §FR-001]
- [ ] CHK003 - Are requirements defined for the Policy Management page's behavior for intake and nurse roles — specifically, is the entire page hidden from the sidebar, or is a read-only view shown with upload/edit controls absent? FR-040 specifies read-only access but the spec does not define the navigation visibility rule for these roles. [Completeness, Spec §FR-040]
- [ ] CHK004 - Is a requirement defined for the initial landing page after successful login — does each role land on a different default page (e.g., intake → Case Management, nurse → Nurse Review), or does every role land on the same page? [Completeness, Gap]

---

## Requirement Completeness — Nurse Review & Lock

- [ ] CHK005 - Is a requirement specified for what the nurse UI displays when a case is in "Pipeline Error" status and appears in a non-queue context (e.g., a case the nurse previously worked on) — does the nurse see a warning, a partial completeness table, or nothing? [Completeness, Gap, Spec §Edge Cases]
- [ ] CHK006 - Is there a requirement for how the nurse's view updates when their lock is auto-released by the background job while they still have the case detail page open — are they notified in-session (banner, modal), or do they only discover the release when they next attempt an action? [Completeness, Gap, Spec §FR-032]
- [ ] CHK007 - Are requirements defined for the "Release" button that explicitly unlocks a case — specifically, is this button always visible while a nurse holds the lock, and does clicking it navigate away from the case or keep the nurse on the (now unlocked) case detail? [Completeness, Gap, contracts/nurse-review.md]
- [ ] CHK008 - Does the spec define the behavior of the nurse queue when a case transitions from "pending_review" to another status while the nurse is viewing the queue (e.g., another nurse claims it between a poll and a page render) — is stale queue data acceptable, or is a real-time update mechanism required? [Completeness, Gap, Spec §FR-030]

---

## Requirement Completeness — Admin Edit & Re-Queue

- [ ] CHK009 - Is a requirement defined for whether the admin can edit case fields *while a nurse holds the active lock* — the Edge Cases section says "admin's edit is permitted (admin override)" but there is no corresponding FR that specifies this path as a normative requirement, only an edge-case description. [Completeness, Gap, Spec §Edge Cases, Spec §FR-052]
- [ ] CHK010 - Are the fields that the admin is permitted to edit explicitly enumerated — specifically, can the admin change the `policy_id` on a case, and if so, what happens to the existing completeness report (is it invalidated and a re-run triggered)? [Completeness, Gap, Spec §FR-052, contracts/admin.md]
- [ ] CHK011 - Is a requirement defined for whether the admin's mandatory comment (FR-053) has a minimum length, a maximum length, or only a "non-empty" constraint — is a single space character a valid comment? [Clarity, Spec §FR-053]
- [ ] CHK012 - Does the spec define what "Admin Edit" badge looks like and where on the case detail it appears — is it a colored label at the top of the page, a banner, or an icon in the queue list? Without a visual specification, the requirement "badge and the admin's comment visible at the top" is ambiguous in implementation. [Clarity, Spec §FR-038, US4 Acceptance Scenario 4]

---

## Requirement Completeness — Policy Management

- [ ] CHK013 - Is a requirement defined for what happens between the moment an admin uploads a policy PDF and the moment the AI-generated draft checklist becomes available — does the admin see a loading state, an estimated wait time, or are they redirected to a polling view? [Completeness, Gap, Spec §FR-042, contracts/policies.md]
- [ ] CHK014 - Is a requirement defined for what the admin UI shows if policy requirement extraction fails (pipeline error on the policy side) — can the admin retry extraction, enter requirements manually without AI, or is the upload considered failed and must be re-uploaded? [Completeness, Gap, Spec §FR-042]
- [ ] CHK015 - Does the spec define whether the policy overwrite on re-upload (FR-044) happens at the point of upload or at the point of the admin saving the finalized requirement checklist — specifically, if the admin uploads a file under an existing policy name but then abandons the draft without saving, is the original policy overwritten or preserved? [Clarity, Spec §FR-044]
- [ ] CHK016 - Is a requirement specified for the confirmation step before policy overwrite — does the admin receive a warning ("A policy named X already exists — uploading will overwrite it") before the overwrite takes effect, or does overwrite happen silently? [Completeness, Gap, Spec §FR-044]

---

## Requirement Clarity

- [ ] CHK017 - Is "non-actionable" (Spec §FR-033) for cases locked by another nurse precisely defined — does it mean the case row in the queue is visually greyed out but still clickable (opening a read-only view), or is the row non-clickable altogether? [Clarity, Spec §FR-033]
- [ ] CHK018 - Is "immediately" in FR-045 ("saved policies MUST be immediately available in the case creation policy dropdown") defined with a measurable latency bound — or does it rely on a cache invalidation or real-time fetch that could introduce a lag? [Clarity, Spec §FR-045]
- [ ] CHK019 - Is "Extracted using OCR" tag in FR-035 defined with enough visual specificity to be testable — what element type (badge, tooltip, asterisk, icon), color, and position relative to the evidence excerpt is required? [Clarity, Spec §FR-035, SC-008]
- [ ] CHK020 - Is "visible" in SC-008 ("every OCR-sourced evidence excerpt … carries a visible 'Extracted using OCR' tag") defined in terms of WCAG contrast ratio or minimum text size so that "visible" is objectively verifiable for accessibility review? [Clarity, Measurability, Spec §SC-008]

---

## Requirement Consistency

- [ ] CHK021 - Are the Accepted and Rejected tab requirements in FR-030 consistent with the nurse queue contract in contracts/nurse-review.md — specifically, does the `/decided` endpoint support separate filtering by `accepted` and `rejected`, matching the two-tab UI described in the spec? [Consistency, Spec §FR-030, contracts/nurse-review.md]
- [ ] CHK022 - Is the "Admin Edit" badge described consistently between US4 Acceptance Scenario 2/4, FR-038, and the PATCH response contract in contracts/admin.md — all three sources use the label, but does the spec define a single canonical display term, or could an implementer display "Admin Edited" and still be compliant? [Consistency, Spec §FR-038, US4, contracts/admin.md]
- [ ] CHK023 - Do the case status values used in the UI (`status` field in contracts/cases.md: `processing`, `pending_review`, `pipeline_error`, `accepted`, `rejected`) match the ENUM defined in data-model.md §cases exactly — or is there a discrepancy (e.g., data model uses `"accepted"` but FR-030 references the tab as "Accepted" capitalized without specifying the canonical machine-readable value)? [Consistency, data-model.md §cases, contracts/cases.md, Spec §FR-030]
- [ ] CHK024 - Is the escalation badge/highlighting requirement for the Admin All Cases table consistent between FR-027 and the RBAC constraint — specifically, is the escalation filter in `/api/v1/admin/cases` restricted to admin role only (consistent with the admin-only base path) or should nurses also be able to see escalation flags in their queue? [Consistency, Spec §FR-027, contracts/admin.md, contracts/nurse-review.md]

---

## Acceptance Criteria Quality

- [ ] CHK025 - Is SC-005 ("in no scenario can two nurses simultaneously hold an active lock on the same case") measurable — does the spec define the mechanism (atomic conditional UPDATE) that enforces this, so a test can be designed that exercises the concurrent claim path directly? [Measurability, Spec §SC-005, research.md §5]
- [ ] CHK026 - Is SC-007 ("zero cases with a nurse decision are routed anywhere other than the nurse review queue after an admin edit") measurable — does it include the edge case where the admin edits a case that is currently locked by a nurse (admin override path), and is 100% routing reliability verifiable end-to-end? [Measurability, Spec §SC-007, Spec §Edge Cases]
- [ ] CHK027 - Are acceptance criteria defined for the light-theme design — specifically, are there minimum WCAG contrast ratio requirements (e.g., 4.5:1 for normal text, 3:1 for large text) stated in the spec, or is visual design quality left entirely to the implementer's judgment? [Measurability, Gap]
- [ ] CHK028 - Is there a measurable acceptance criterion for keyboard accessibility of the core workflow — e.g., can the full intake → submit path and the nurse → accept path be completed without a mouse? Is keyboard navigation explicitly required for the lock, heartbeat, and decision actions? [Measurability, Gap]

---

## Scenario Coverage — Lock Race Conditions

- [ ] CHK029 - Does the spec define the *error message content* that Nurse B sees when they attempt to claim a case already locked by Nurse A — is it required to include the locking nurse's name and an estimated lock expiry time, or only a generic "case is locked" message? [Coverage, Spec §FR-033, contracts/nurse-review.md]
- [ ] CHK030 - Are requirements defined for the nurse's UX when the 409 lock-conflict response is returned — does the UI show a modal, an inline error, or a toast notification? Is auto-retry (e.g., try again after lock expires) a requirement or optional? [Coverage, Gap, contracts/nurse-review.md]
- [ ] CHK031 - Is the concurrent lock claim scenario (two nurses click a case simultaneously) covered in the spec's acceptance criteria with a defined expected outcome for each of the two requesting users — not just for the winner? [Coverage, Spec §Edge Cases]

---

## Edge Case Coverage

- [ ] CHK032 - Are requirements defined for the case detail view's behavior when the completeness pipeline is still running (`status = "processing"`) but a nurse navigates to the case — does the RAG Summary tab show a loading state, a "not yet available" message, or is the case not accessible from the nurse queue until pipeline completes? [Edge Case, Spec §FR-030, Spec §FR-034]
- [ ] CHK033 - Does the spec define the nurse UI behavior when a case has zero documents (e.g., a case where all uploads failed) — specifically, does the Document Viewer show an empty state message or an error, and are requirements consistent with the fact that the completeness report would also be empty? [Edge Case, Gap]
- [ ] CHK034 - Is a requirement defined for the policy overwrite confirmation's behavior if the overwriting upload's extraction also fails — is the original policy restored, or is the policy left in a partially-overwritten state with no requirements? [Edge Case, Gap, Spec §FR-044]
- [ ] CHK035 - Is the behavior specified for the intake case creation form when the upload-session has expired on the server (e.g., the associate uploaded documents, navigated away, returned an hour later, and submitted) — does the session expire, and if so, what does the form show? [Edge Case, Gap, contracts/cases.md §POST /api/v1/cases]

---

## Non-Functional Requirements

- [ ] CHK036 - Are loading/skeleton-state requirements defined for the nurse RAG Summary view — given that the completeness report may contain many requirement rows, is there a requirement for progressive rendering or a minimum time-to-first-content? [Gap, Non-Functional]
- [ ] CHK037 - Are requirements defined for the Document Viewer's page-navigation behavior on large PDFs — is there a page count upper bound, a requirement for lazy/on-demand page loading, or is the viewer required to load all pages upfront? [Gap, Non-Functional, Spec §FR-036]
- [ ] CHK038 - Is an error boundary / graceful degradation requirement specified for the frontend — if the backend returns a 500 or is temporarily unreachable, does the spec require a specific error UI rather than a blank page or unhandled exception? [Gap, Non-Functional]
