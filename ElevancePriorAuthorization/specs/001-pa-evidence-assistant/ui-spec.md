# UI Specification

## Intake Dashboard
- **Target User**: Provider Relations / Intake Associate
- **Purpose**: Upload case documents and manually enter metadata.
- **Components**:
  - File Dropzone for PDFs/Scans.
  - Form fields: Member ID, Provider ID, CPT Code, ICD-10 Code, Service Type.
  - "Submit Case" Button.
  - Status list showing recently submitted cases and their automated completeness check status (Pending Check, Ready for Nurse Review).

## Operations Dashboard
- **Target User**: Operations Manager / Compliance Audit User
- **Purpose**: High-level queue monitoring and SLA tracking.
- **Components**:
  - Queue statistics (Unassigned, Claimed, SLA Breached, Escalated).
  - Search/Filter by Member ID, CPT Code.
  - Case detail view with full `AuditLog` read-only access (showing timestamps, agents, prompts, and nurse identities).

## Nurse Review Workspace
- **Target User**: Nurse Reviewer / Medical Director
- **Purpose**: Independent case assessment and final human decision.
- **Components**:
  - **Left Panel (Case Summary)**: Member/Provider metadata, policy version active for this case.
  - **Center Panel (Document Viewer)**: In-app PDF viewer. Supports zooming, pagination, and highlighting (via coordinates provided by the citation).
  - **Right Panel (Completeness Checklist)**: The system-generated report. Each item shows Present/Absent/Unclear with confidence scores. Clicking a citation navigates the Center Panel viewer to the exact page/chunk.
  - **Action Footer**:
    - "Override" button next to checklist items to manually toggle status.
    - **Accept Button**: Finalizes the case. Irreversible once submitted.
    - **Reject Button**: Opens a modal requiring a structured reason code dropdown and a mandatory free-text notes field. Seeds a draft communication.
