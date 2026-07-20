# Feature Specification: Elevance Prior Authorization Evidence Assistant (v2)

**Feature Branch**: `001-pa-evidence-assistant`

**Created**: 2026-07-20

**Status**: Draft

**Input**: User description: "Build the Elevance Prior Authorization Evidence Assistant..."

---

## Clarifications

### Session 2026-07-20

- Q: How does the frontend communicate pipeline status while a case is processing? → A: Periodic polling — the frontend polls a case-status endpoint every 5–10 seconds while the case is in "Processing" state and stops automatically once the status resolves to a terminal state (Ready for Review, Pipeline Error, Accepted, Rejected). No WebSocket or SSE connection is required.
- Q: What constitutes "inactivity" for the 30-minute nurse lock auto-release? → A: Heartbeat-based — while a case is open, the frontend sends a heartbeat ping to `/cases/{id}/heartbeat` every 2 minutes to refresh a `last_active_at` timestamp on the lock record. The auto-release background job determines expiry as `now − last_active_at > 30 minutes`. No mouse-movement tracking required.
- Q: Are access tokens blacklisted on logout, or is expiry-only relied upon? → A: Stateless access tokens (15-min expiry, no blacklist). On logout, the refresh token is revoked server-side by setting a `revoked` flag on its stored hashed record. A maximum 15-minute blast radius on a leaked access token is acceptable for this internal staff tool.
- Q: When SLA time expires, which queue does the case move to and what can staff do with it? → A: No separate escalation queue — escalated cases remain in the Nurse Review queue, flagged `is_escalated` and sorted to the top (escalated-first, then oldest-first). The Admin All Cases view highlights overdue cases and supports filtering by escalation status.
- Q: Which case fields are mandatory vs. optional for submission? → A: **Member ID** and **Requested Service/Procedure** are hard-required (either AI-extracted or manually entered). CPT/HCPCS Code, ICD-10 Code, Provider Name, and Requested Date are optional at submission and may be left blank.

---

## Constitution Alignment *(mandatory)*

| Principle | Applicable? | Notes / Constraints for this Feature |
|-----------|-------------|---------------------------------------|
| I – On-Premises Inference | Yes | All LLM calls, embeddings, and OCR must run on the local host. No external AI/storage API may be introduced anywhere in the stack. |
| II – Human-Only Routing | Yes | Every case unconditionally routes to nurse review. No automated approve/deny logic anywhere. Nurse Accept/Reject is a documentation-completeness routing decision only. |
| III – Auth & Authz | Yes | Every route requires a valid JWT and an explicit role check. No unauthenticated endpoints exist. Intake, nurse, and admin roles are all gated separately. |
| IV – LLM Sizing | Yes | phi4-mini (3.8B) primary, llama3.2:3b alternate. JSON-mode / structured output must be preferred over larger models. |
| V – Hybrid Extraction | Yes | PyMuPDF native extraction first per page; EasyOCR GPU fallback for near-empty pages. Chunks carry extraction_method provenance. OCR-sourced evidence is visibly tagged in the nurse UI. |
| VI – Best-Effort Fields | Yes | Case field auto-extraction leaves unconfident fields blank — no guessing or defaulting. |
| VII – Confidence Bands | Yes | Present ≥ 85%, Absent < 70%, Unclear in between. No raw probability display to end users. |
| VIII – Hybrid Retrieval | Yes | Identifier requirements → PostgreSQL exact/BM25; narrative requirements → dense semantic search; mixed → RRF + keyword-miss cap (cap at Unclear when keyword miss on identifier-bearing requirement). |
| IX – Policy Management | Yes | Upload restricted to admin. AI extraction is a draft; admin can add/edit/delete requirement rows before saving. Overwrite on re-upload with same name. |
| X – Case Editing & Audit | Yes | Admin may edit any case. Editing a decided case requires a mandatory comment and re-queues it tagged "Admin Edit". Original decision preserved in audit log. |
| XI – Nurse Locking | Yes | Opening a case for review acquires an exclusive nurse lock with 30-min inactivity auto-release. |
| XII – Infra Ceiling | Yes | Exactly 2 Docker containers (postgres, qdrant). Ollama and EasyOCR run natively on the host GPU. |
| XIII – Secrets Abstraction | Yes | All secrets (DB credentials, JWT keys, paths) flow through the single secrets-abstraction module. |
| XIV – Schema Discipline | Yes | Every schema change ships as a new Alembic migration. No applied migrations are edited. |

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 – Intake Associate Creates a PA Case (Priority: P1) 🎯 MVP

An intake associate logs in and is immediately presented with the Case Management area. They click **"+ New Case"** and first upload one or more PDF documents (clinical notes, referral letters, prior authorization request forms, faxes, scans). The system extracts text from each document — natively for text-based pages and via OCR for scanned/image pages — and passes the extracted text through an AI extraction pass. Within moments, the new-case form pre-fills whichever of the following fields were confidently found: **Member ID**, **Provider**, **CPT/HCPCS Code**, **ICD-10 Code**, **Requested Service/Procedure**, and **Requested Date**. Fields the AI could not confidently locate remain blank and visually indistinguishable from unfilled fields (no false confidence indicators). Pre-filled fields are clearly labeled "AI-extracted — please verify." The associate reviews, corrects if needed, and selects the applicable policy from a dropdown sorted and displayed by policy name (no policy IDs visible). They submit. The case is created immediately, the completeness analysis pipeline starts in the background, and the associate sees a "Case submitted — analysis in progress" confirmation.

**Why this priority**: This is the entry point of the entire workflow. Without it, no cases can flow into the system. All downstream personas (nurse, admin) depend on it.

**Independent Test**: An intake associate can upload a PDF containing a clinical note, confirm that Member ID and CPT fields auto-populate, clear one auto-populated field, add a value to a blank field, select a policy by name, and submit — receiving a case-created confirmation — with no downstream nurse or admin action required.

**Acceptance Scenarios**:

1. **Given** an intake associate is logged in, **When** they upload a native-text PDF containing "Member ID: M123456" and CPT "72148", **Then** the Member ID field is pre-filled with "M123456" and CPT is pre-filled with "72148", both labeled "AI-extracted — please verify."
2. **Given** the uploaded PDF is a scanned fax with no embedded text, **When** the system processes it, **Then** OCR is applied and any confidently extracted fields are pre-filled; an evidence-level OCR tag is recorded so it can be surfaced later in the nurse UI.
3. **Given** the LLM cannot confidently locate the ICD-10 code in the document, **When** the form renders, **Then** the ICD-10 field is blank — not pre-filled with a guess or a default value.
4. **Given** the intake associate submits a valid case, **When** submission completes, **Then** a confirmation is shown, the case appears in the case list with status "Processing," and the background completeness pipeline starts automatically.
5. **Given** multiple policies exist in the system, **When** the intake associate opens the policy dropdown, **Then** policies are listed alphabetically by name and no policy IDs are visible.

---

### User Story 2 – Nurse Reviews a Case and Makes a Decision (Priority: P1) 🎯 MVP

A nurse logs in and sees the **Nurse Review** area. The **Queue** tab shows all unclaimed cases (status "Ready for Review") and any cases they personally have locked. The nurse clicks on an unclaimed case — the system acquires a lock on that case for this nurse, and all other nurses immediately see the case greyed out as "Locked by [Nurse Name]." Inside the case, the nurse can toggle between two views: the **RAG Summary** view (an AI-generated narrative case summary at the top, followed by a per-requirement completeness table showing each policy requirement with its verdict — Present, Absent, or Unclear — and supporting evidence excerpts, with any OCR-sourced excerpt visibly tagged "Extracted using OCR") and the **Document Viewer** (the original PDFs, displayed page by page). The nurse can switch freely between views. Satisfied with their review, the nurse clicks **Accept** or **Reject**. This is a documentation-completeness and routing decision only — not a clinical approval or denial. The case moves to the **Accepted** or **Rejected** tab accordingly.

**Why this priority**: The nurse review step is the core human-in-the-loop clinical triage action. It is the primary purpose of the entire system.

**Independent Test**: A nurse can log in, claim a case from the queue, view the RAG summary with verdict table, toggle to the PDF viewer to inspect page 2 of an uploaded document, and click Accept — all without any admin action. Acceptance moves the case to the Accepted tab and releases the lock.

**Acceptance Scenarios**:

1. **Given** a case has completed its background pipeline, **When** a nurse opens the Queue tab, **Then** the case appears as unclaimed and actionable.
2. **Given** a nurse opens a case, **When** the case detail loads, **Then** the nurse holds an exclusive lock and a 30-minute inactivity countdown begins.
3. **Given** Nurse A has locked a case, **When** Nurse B views the queue, **Then** the case appears in Nurse B's list as "Locked by [Nurse A's Name]" and is non-actionable.
4. **Given** a nurse has been inactive for 30 minutes on a case, **When** another nurse tries to open it, **Then** the lock has been auto-released and the case is claimable.
5. **Given** a requirement in the completeness table has confidence 0.89, **When** it is displayed, **Then** its verdict badge reads "Present."
6. **Given** a requirement has confidence 0.65, **When** displayed, **Then** its verdict reads "Unclear."
7. **Given** a requirement has confidence 0.55, **When** displayed, **Then** its verdict reads "Absent."
8. **Given** evidence for a requirement was sourced from an OCR-processed page, **When** the evidence excerpt is shown in the RAG summary, **Then** an "Extracted using OCR" tag is visible on that evidence item.
9. **Given** a nurse clicks Accept, **When** the action completes, **Then** the case moves to the Accepted tab and is no longer in the Queue.

---

### User Story 3 – Admin Uploads and Edits a Policy (Priority: P2)

An admin navigates to **Policy Management** and uploads a new policy PDF, providing a mandatory human-readable policy name (e.g., "Lumbar Spine MRI — 2026"). The system extracts text from the policy document (same native + OCR fallback pipeline) and an AI pass converts the policy into a structured checklist of requirements. The checklist is shown to the admin as an editable draft — each row shows the requirement description. The admin can add a row the AI missed, edit a misread requirement, or delete a spurious row. When satisfied, the admin saves. If they re-upload a file under the same policy name, the existing policy and its requirement checklist are overwritten. Non-admin users (intake, nurse) can view the policy list and read the requirement checklists, but cannot upload, edit, or delete.

**Why this priority**: Policy requirements drive the entire completeness analysis. This must exist before any nurse review can be meaningful, but intake case creation can work (with a policy already loaded) without this workflow having been exercised in the current session.

**Independent Test**: An admin can upload a policy PDF, see the AI-generated checklist, add one row, delete one AI-generated row, edit one row's text, and save — producing a finalized policy available in the intake case creation dropdown.

**Acceptance Scenarios**:

1. **Given** an admin uploads a policy PDF with name "Lumbar Spine MRI — 2026", **When** processing completes, **Then** an editable checklist of extracted requirements is presented.
2. **Given** the AI extraction missed a requirement, **When** the admin adds it manually and saves, **Then** the saved policy checklist includes the manually added requirement.
3. **Given** an admin re-uploads a file under the name "Lumbar Spine MRI — 2026", **When** they save, **Then** the existing policy's checklist is overwritten (no duplicate or version is created).
4. **Given** a nurse is logged in and navigates to Policy Management, **When** they view the policy list and a policy's checklist, **Then** no upload, edit, or delete controls are visible or accessible.
5. **Given** a policy is saved, **When** an intake associate creates a new case, **Then** that policy name appears in the policy dropdown.

---

### User Story 4 – Admin Edits a Decided Case and Re-Routes for Fresh Review (Priority: P2)

An admin views the Admin area's All Cases table and identifies a case that was previously accepted. The admin opens it and edits a field (e.g., updates the ICD-10 code). Because the case already has a decision, the system requires the admin to enter a mandatory comment explaining the change. On save, the case is re-queued in the Nurse Review queue, displayed with an **"Admin Edit"** badge and the admin's comment visible at the top of the case detail. The original acceptance remains in the audit log — it is not deleted or overwritten. Any nurse can now pick up the case for a fresh review.

**Why this priority**: This supports the audit and correction workflow. It cannot be exercised until at least one case has been through a nurse review cycle (US2), so it is P2.

**Independent Test**: An admin can open an accepted case, submit an edit with a mandatory comment, and verify that (a) the case reappears in the Nurse Review queue, (b) an "Admin Edit" badge and the comment are visible, and (c) the audit log still contains the original acceptance event.

**Acceptance Scenarios**:

1. **Given** a case has status "Accepted", **When** an admin edits any field without entering a comment, **Then** the save action is blocked with a "Comment required" validation message.
2. **Given** an admin edits an accepted case and provides a comment, **When** saved, **Then** the case appears in the Nurse Review queue tagged "Admin Edit" with the comment visible.
3. **Given** the admin edited case has been re-queued, **When** the audit log is viewed, **Then** both the original "Accepted" event and the "Admin Edit" event are present, with the original not overwritten.
4. **Given** the re-queued admin-edited case appears in the nurse queue, **When** any nurse opens it, **Then** they see the "Admin Edit" badge and comment at the top of the case detail.

---

### User Story 5 – Admin Manages Staff Accounts and Views Audit Log (Priority: P3)

An admin uses the Admin area to create a new staff account (assigning a role of intake, nurse, or admin), deactivate an existing account, and reset a user's password. The admin can also browse the Audit Log — a searchable, chronological, immutable list of every significant system event: case status changes, AI pipeline calls with their inputs and confidence scores, nurse decisions, admin edits, and authentication events. The audit log cannot be edited or deleted by any user.

**Why this priority**: User management and audit browsing are operational necessities but do not block the core PA review workflow. They can be delivered after the primary case lifecycle is functional.

**Independent Test**: An admin can create a new nurse account, log out, log in as the new nurse, confirm access to the Nurse Review area, then log back in as admin and view the new nurse's login event in the audit log.

**Acceptance Scenarios**:

1. **Given** an admin creates a new account with role "nurse", **When** that user logs in, **Then** they have access to Nurse Review and Case Management (read), but not Admin or Policy Management write controls.
2. **Given** an admin deactivates an account, **When** that user attempts to log in, **Then** authentication is denied.
3. **Given** a case was accepted two hours ago, **When** an admin searches the audit log by case ID, **Then** all events for that case appear in chronological order: case creation, pipeline start, pipeline complete, nurse claim, nurse accept.
4. **Given** any user views the audit log, **When** they attempt to delete or edit an entry, **Then** no such control is available and no API endpoint permits it.

---

### Edge Cases

- What happens when a PDF upload contains a mix of native-text pages and scanned pages? → Each page is processed independently; the form shows pre-filled fields from whichever pages yielded results; the chunk metadata records the source type per page.
- What happens when the completeness pipeline encounters an LLM timeout or failure? → The case remains in "Processing" state. After a configurable retry window, if the pipeline still fails, the case is flagged "Pipeline Error." The frontend's polling mechanism (FR-018) surfaces this status automatically without a manual refresh — the status badge updates within the next polling interval. An admin can view the case in the Admin All Cases table and trigger remediation; the case never silently disappears.
- What happens if two nurses simultaneously try to lock the same unclaimed case? → The lock is acquired exclusively by the first to succeed; the second receives a message that the case is now locked by the other nurse.
- What happens if an admin edits a case that is currently locked by a nurse? → The admin's edit is permitted (admin override), the lock is released, and the nurse's session shows a notification that the case was modified and re-queued.
- What happens if a policy is deleted while cases referencing it are still in the review queue? → Existing cases retain their snapshot of the policy requirements at time of case creation and can still be reviewed and decided normally. The deleted policy is no longer available in the dropdown for new cases.
- What happens if the AI extraction of case fields returns no confident results at all? → All fields remain blank; the form is entirely manual. Submission is still possible as long as Member ID and Requested Service/Procedure are provided manually, and a policy is selected from the dropdown.
- What if the OCR pass also fails to extract readable text from a page? → The chunk is still created but with empty text and a flag indicating extraction failure; the nurse is notified that one page of a document could not be read and should be reviewed in the PDF viewer directly.

---

## Requirements *(mandatory)*

### Functional Requirements

#### Authentication & Authorization

- **FR-001**: The system MUST provide a single login page accessible to all staff roles. All other pages MUST redirect unauthenticated users to login.
- **FR-001a**: The system MUST enforce lightweight brute-force protection on the login endpoint: 5 failed attempts per username per 15 minutes, tracked in PostgreSQL, followed by a lockout.
- **FR-002**: The system MUST issue a short-lived access token (JWT) and a longer-lived refresh token upon successful credential verification. Tokens MUST include user identity and role claims.
- **FR-003**: Every API endpoint and UI route MUST enforce authentication. Endpoints MUST additionally enforce role-based access, rejecting requests from users without the required role with a "403 Forbidden" response.
- **FR-004**: The system MUST support three roles: **Intake Associate** (create cases, view cases, view policies read-only), **Nurse** (view cases, lock/review/decide cases, view policies read-only), **Admin** (all intake and nurse capabilities plus: edit any case, manage users, manage policies, view audit log).
- **FR-005**: The system MUST hash stored passwords using argon2id with explicit minimum parameters: `time_cost=3`, `memory_cost=65536` (64MB), and `parallelism=4`. Plaintext passwords MUST never be stored or logged.
- **FR-006**: On user logout, the associated refresh token MUST be revoked server-side by setting a `revoked` flag on its stored hashed record. Access tokens are stateless and are not blacklisted; they remain valid until their 15-minute natural expiry. No token blacklist table is required.
- **FR-006a**: Role changes made by an admin mid-session take effect on the user's next token refresh. The existing 15-minute access token retains the old role until it expires.

#### Case Management (Intake Flow)

- **FR-010**: The system MUST allow an authenticated intake associate to upload one or more PDF documents before filling in case fields.
- **FR-011**: Upon document upload, the system MUST attempt native text extraction per page first. Pages with < 20 characters of native-extracted text (after whitespace strip) MUST trigger GPU-accelerated OCR as a fallback.
- **FR-012**: The extracted text MUST be chunked into 512-token segments with a 50-token overlap. Each extracted text chunk MUST carry provenance metadata indicating whether its text came from native extraction or OCR.
- **FR-013**: After text extraction, the system MUST run an AI extraction pass to identify the following fields if present: Member ID, Provider Name, CPT/HCPCS Code, ICD-10 Code, Requested Service/Procedure, and Requested Date. Fields the AI cannot confidently identify MUST be left blank. The AI MUST NOT populate a field with a guess or a default value.
- **FR-013a**: Of the six case fields, **Member ID** and **Requested Service/Procedure** MUST be provided (either via AI extraction or manual entry) before a case can be submitted. The system MUST block submission and display a validation error if either required field is absent. CPT/HCPCS Code, ICD-10 Code, Provider Name, and Requested Date are optional at submission.
- **FR-014**: Pre-filled fields in the case creation form MUST be visually labeled as "AI-extracted — please verify" and MUST remain editable by the intake associate before submission.
- **FR-015**: The policy selection field MUST be a searchable dropdown listing all available policies sorted alphabetically by policy name. Policy IDs MUST NOT be visible to the user.
- **FR-016**: On case submission, the system MUST create the case record immediately and return a success response to the user. The completeness analysis pipeline MUST run as a background task without blocking the response.
- **FR-017**: The case list MUST display current status (e.g., Processing, Ready for Review, Pipeline Error, Accepted, Rejected) and be searchable and filterable by status, service type, and submission date.
- **FR-018**: While a case is in "Processing" status, the case list and case detail view MUST automatically poll a case-status endpoint every 5–10 seconds. Polling MUST stop automatically once the case transitions to any terminal status. No WebSocket or server-sent event connection is required for this mechanism.

#### Completeness Analysis Pipeline

- **FR-020**: The completeness pipeline MUST, for each case, extract and chunk all uploaded documents, generate embeddings, index chunks into the vector store, and then evaluate each policy requirement against the case evidence.
- **FR-021**: For policy requirements that contain structured identifiers (Member ID, CPT/HCPCS, ICD-10, policy name), the system MUST attempt exact or keyword match against structured data columns first before falling back to vector search.
- **FR-022**: For policy requirements involving clinical narrative, the system MUST use semantic dense vector search to retrieve the most relevant evidence chunks.
- **FR-023**: For mixed requirements, the system MUST combine dense and sparse (BM25) retrieval results using Reciprocal Rank Fusion. The system MUST apply a keyword-miss cap: if a chunk appears in the top-5 dense results for an identifier-bearing requirement but has zero sparse/BM25 hits, the requirement verdict MUST be capped at "Unclear."
- **FR-024**: Each requirement verdict MUST be assigned one of exactly three statuses: **Present** (confidence ≥ 85%), **Absent** (confidence < 70%), **Unclear** (confidence 70–84%). No raw confidence scores MUST be displayed to end users.
- **FR-025**: The pipeline MUST record all intermediate outputs (retrieved chunks, confidence scores, reasoning) in the audit log in association with the case ID.
- **FR-026**: When a case in the Nurse Review queue has exceeded the SLA threshold defined by its associated policy, the system MUST flag the case with an escalation marker (`is_escalated = true`). Escalated cases MUST remain in the Nurse Review queue — no separate escalation queue is created.
- **FR-027**: In the Nurse Review queue, escalated cases MUST be sorted above non-escalated cases (escalated-first, then oldest-first within each group). In the Admin All Cases table, escalated cases MUST be visually distinguished (e.g., highlighted row or badge) and the table MUST support filtering by escalation status.

#### Nurse Review

- **FR-030**: Nurses MUST see a Queue tab listing all unclaimed cases and cases they personally have locked, an Accepted tab, and a Rejected tab.
- **FR-031**: When a nurse opens a case to review it, the system MUST acquire an exclusive lock for that nurse. No other nurse may take a review action on a locked case.
- **FR-032**: The lock MUST auto-release when the locking nurse's session has been inactive for 30 consecutive minutes. Inactivity is measured server-side via a `last_active_at` timestamp on the lock record. While a case is open, the frontend MUST send a heartbeat request to a dedicated lock-heartbeat endpoint approximately every 2 minutes to refresh `last_active_at`. The background auto-release job MUST determine lock expiry as `now − last_active_at > 30 minutes`. Once released, the case becomes claimable by any nurse.
- **FR-033**: Cases locked by another nurse MUST be visible to other nurses in the queue, clearly labeled "Locked by [Nurse Full Name]," but non-actionable.
- **FR-034**: Within a case, nurses MUST be able to toggle between a **RAG Summary view** and a **Document Viewer** at any time without losing their lock or any unsaved state.
- **FR-035**: The RAG Summary view MUST show: (a) a narrative case summary generated by the AI, (b) a per-requirement completeness table with requirement description, verdict badge (Present/Absent/Unclear), and supporting evidence excerpt(s) with source page reference, and (c) an "Extracted using OCR" tag on any evidence excerpt sourced from an OCR-processed chunk.
- **FR-036**: The Document Viewer MUST display the original uploaded PDFs, navigable page by page.
- **FR-037**: Nurses MUST be able to Accept or Reject a case. This action MUST be recorded with the nurse's identity, role, timestamp, and decision. The action is a documentation completeness and routing decision — not a clinical approval or denial.
- **FR-038**: If an admin has re-queued a previously decided case, it MUST appear in the nurse queue with an **"Admin Edit"** badge (an amber/warning-colored pill) and the admin's comment visible at the top of the case detail view (e.g., in a tooltip or expandable area).

#### Policy Management

- **FR-040**: Policy write endpoints (upload, edit, delete, save) MUST strictly reject non-admin roles at the API level (403 Forbidden). As a UI convenience, the frontend MUST display the Policy Management page to intake and nurse users in a read-only mode, hiding all upload and edit controls.
- **FR-041**: Policy upload MUST require the admin to provide a policy name (text field, mandatory).
- **FR-042**: After upload, the system MUST run the same text extraction pipeline (native + OCR fallback) and then an AI pass that converts the policy document into a structured requirement checklist.
- **FR-043**: The AI-generated checklist MUST be presented to the admin as a fully editable draft before saving. The admin MUST be able to add, edit, or delete individual requirement rows.
- **FR-044**: Re-uploading a policy using a name that already exists in the system MUST overwrite the existing policy and its requirement checklist. This MUST require a two-step confirmation: uploading a duplicate name displays an explicit "this will overwrite policy X" warning before committing. Navigating away without confirming does nothing. No versioning or history of the prior policy MUST be retained in the primary data.
- **FR-045**: Saved policies MUST be immediately available in the case creation policy dropdown.

#### Admin

- **FR-050**: Admins MUST have access to a full, searchable, filterable table of all cases in the system regardless of status or assigned queue.
- **FR-051**: The all-cases table MUST display, for each case: case ID, member ID, policy, status, assigned queue, the name of the nurse who has the case locked (if any), and the name and decision of the nurse who last decided the case (if any).
- **FR-052**: Admins MUST be able to edit any case field on any case regardless of its current status.
- **FR-053**: Editing a case that already has a nurse decision (Accepted or Rejected) MUST require the admin to provide a mandatory free-text comment. The save MUST be blocked until a non-empty comment is provided.
- **FR-054**: When an admin saves an edit to a decided case, the system MUST automatically change the case status back to "Ready for Review" and add it to the nurse review queue, tagged with an "Admin Edit" label and the admin's comment.
- **FR-055**: The original nurse decision event MUST remain in the audit log and MUST NOT be deleted or modified.
- **FR-056**: Admins MUST be able to create new user accounts (with name, username, password, and role assignment), deactivate existing accounts, and reset passwords.
- **FR-057**: Admins MUST have access to the audit log: a chronological, searchable (by case ID, user, date range, action type), immutable record of all system events including: case creation, document uploads, pipeline start/complete/error events, AI calls (with model, version, inputs, outputs, confidence scores), nurse lock/unlock, nurse decisions, admin edits, and user authentication events.
- **FR-058**: No user of any role MUST be able to delete or modify an audit log entry through any UI or API endpoint.

#### User Interface & Accessibility

- **FR-060**: The frontend UI MUST adhere to WCAG 2.1 AA contrast standards: at least 4.5:1 for normal text and 3:1 for large text and UI components.

### Key Entities

- **User**: Authenticated staff member with a role (intake, nurse, admin). Has an identity, role, creation timestamp, and active/inactive status.
- **Case**: A single prior authorization request. Has member ID (required), requested service/procedure (required), provider name (optional), CPT/HCPCS code (optional), ICD-10 code (optional), requested date (optional), associated policy, current status, queue assignment, lock state (locked by, locked at, last_active_at), escalation flag (`is_escalated`), decision (decided by, decided at, decision type), and a history of status transitions.
- **Document**: An uploaded PDF associated with a case. Stored on local filesystem. Has a file reference, upload timestamp, and a set of extracted text chunks.
- **Chunk**: A segment of text extracted from a document page. Carries: document ID, case ID, page number, chunk position, text, and extraction method (native or OCR).
- **Policy**: An uploaded policy document with a human-readable name. Has a set of requirement rows and a timestamp.
- **PolicyRequirement**: A single evidence criterion extracted from a policy. Has a description, requirement type (identifier or narrative), and optional matching criteria.
- **CompletenessReportItem**: The result of evaluating one policy requirement against one case. Has: case ID, requirement ID, verdict (Present/Absent/Unclear), confidence score, supporting evidence chunks, and reasoning log.
- **AuditLog**: An immutable record of a single system event. Has: event type, actor identity and role, case ID (if applicable), timestamp, and a structured payload capturing before/after state or AI call metadata.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An intake associate can create a new case — including document upload, AI field pre-fill review, policy selection, and submission — in under 3 minutes for a typical single-document case.
- **SC-002**: AI field extraction correctly identifies at least 4 of the 6 targeted fields on a well-structured, native-text clinical note PDF without manual correction.
- **SC-003**: The completeness pipeline completes for a typical 3-document case within 5 minutes of submission on the designated hardware.
- **SC-004**: A nurse can locate a case in their queue, review the RAG summary, inspect the source PDF, and record an Accept or Reject decision in under 10 minutes for a typical case with a clear completeness picture.
- **SC-005**: The nurse case lock prevents concurrent edits: in no scenario can two nurses simultaneously hold an active lock on the same case.
- **SC-006**: After a nurse is inactive for 30 minutes, the lock releases and the case becomes claimable by another nurse within 5 seconds of the timeout expiring.
- **SC-007**: Zero cases with a nurse decision are routed anywhere other than the nurse review queue after an admin edit — the admin-edit re-queue path must have 100% reliability.
- **SC-008**: Every OCR-sourced evidence excerpt displayed in the nurse RAG summary carries a visible "Extracted using OCR" tag — no OCR evidence appears without this tag.
- **SC-009**: The audit log retains a complete event record for every case that has been through at least one status transition, with no events missing or out of order.
- **SC-010**: All system routes enforce authentication; an unauthenticated HTTP request to any non-login endpoint returns a 401 response within 200ms.

---

## Assumptions

- The system is deployed and operated by a single payer organization on a single on-premises Windows host. Multi-tenant or multi-site deployment is out of scope.
- The user base is small (a handful of intake associates, nurses, and admins). The system is not designed for hundreds of concurrent users and does not need horizontal scaling.
- Providers submit cases indirectly through intake associates using the application UI, not through a direct provider-facing API. A provider-facing intake API is out of scope for this version.
- All uploaded documents are PDFs. Other file types (DOCX, images, HL7, FHIR) are out of scope for v2.
- The system operates in English only. Multi-language support is out of scope.
- The LLM (phi4-mini) operates in a JSON-structured output mode and is expected to produce valid JSON on every call. The application will retry on malformed responses up to a configured limit before marking the pipeline as failed.
- A SLA escalation mechanism (auto-escalating cases that sit in the review queue beyond a time threshold) is part of the background infrastructure inherited from the v1 architecture (SLA service) and is included in scope. Escalated cases are flagged `is_escalated` and sorted to the top of the single Nurse Review queue — no separate escalation queue is created. The SLA threshold is defined per policy (default: 48 hours, inherited from v1).
- Medical Director and Provider Relations personas from the domain model (see Elevance Sample Usecase.docx) are **out of scope** for v2: the system serves only Intake Associates, Nurses, and Admins. Medical Director review queue and provider-facing communications are deferred.
- The Operations Manager dashboard (queue volumes, SLA breach alerts, system health) is in scope as part of the Admin area's all-cases table and audit log, not as a separate dedicated page.
- The existing v1 source code and architecture (5-agent Python backend, FastAPI, Alembic, Qdrant, PostgreSQL) is the starting point. The v2 rebuild changes implementations and adds new workflows but preserves the agent-based structure and module layout.
