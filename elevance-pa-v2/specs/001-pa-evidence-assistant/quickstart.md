# Quickstart & Validation Guide: Elevance PA Evidence Assistant (v2)

**Feature**: `001-pa-evidence-assistant`
**Date**: 2026-07-20
**Purpose**: Runnable validation scenarios that prove the end-to-end feature works. Not a full implementation guide — implementation details live in `tasks.md`.

---

## Prerequisites

### 1. Infrastructure

```powershell
# Start PostgreSQL + Qdrant (the only two Docker containers)
cd backend
docker-compose up -d

# Verify containers
docker-compose ps
# Expected: postgres (healthy), qdrant (healthy)
```

### 2. Database

```powershell
# Apply all Alembic migrations
cd backend
python -m alembic upgrade head

# Verify tables
python -c "
from sqlalchemy import create_engine, inspect
from src.core.config import settings
e = create_engine(settings.database_url.replace('+asyncpg',''))
tables = inspect(e).get_table_names()
expected = {'users','refresh_tokens','cases','case_status_history','documents',
            'policies','policy_requirements','completeness_report_items','audit_logs'}
missing = expected - set(tables)
print('PASS: all tables present' if not missing else f'FAIL: missing {missing}')
"
```

### 3. Qdrant Collection

```powershell
python -c "
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
client = QdrantClient(host='localhost', port=6333)
cols = [c.name for c in client.get_collections().collections]
print('PASS: pa-evidence collection exists' if 'pa-evidence' in cols else 'FAIL: collection missing')
"
```

### 4. Ollama

```powershell
# Verify models are pulled and responsive
curl http://localhost:11434/api/tags
# Expected: phi4-mini and nomic-embed-text appear in response

# Quick smoke test
curl -X POST http://localhost:11434/api/generate -d '{"model":"phi4-mini","prompt":"Reply OK","stream":false}'
# Expected: response containing "OK"
```

### 5. Seed Data

```powershell
# Create the first admin user
cd backend
python scripts/seed_admin.py --username admin --password AdminPass1! --full-name "Admin User"
```

### 6. Backend Server

```powershell
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# Expected: "Application startup complete" in logs
```

### 7. Frontend

```powershell
cd frontend
npm install
npm run dev
# Expected: Vite dev server at http://localhost:5173
```

---

## Validation Scenario 1: Authentication (FR-001 through FR-006)

### 1a. Login returns tokens

```powershell
$creds = @{ username="admin"; password="AdminPass1!"; grant_type="password" }
$response = Invoke-RestMethod -Method POST `
  -Uri "http://localhost:8000/api/v1/auth/token" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body $creds

# PASS if both tokens present
$response.access_token -ne $null
$response.refresh_token -ne $null
```

### 1b. Unauthenticated request returns 401 (SC-010)

```powershell
try {
  Invoke-RestMethod -Uri "http://localhost:8000/api/v1/cases"
} catch {
  $_.Exception.Response.StatusCode -eq 401  # PASS
}
```

### 1c. Logout revokes refresh token (FR-006)

```powershell
# Logout
Invoke-RestMethod -Method POST `
  -Uri "http://localhost:8000/api/v1/auth/logout" `
  -Headers @{Authorization="Bearer $($response.access_token)"} `
  -Body (@{refresh_token=$response.refresh_token} | ConvertTo-Json) `
  -ContentType "application/json"

# Attempt to use revoked refresh token
try {
  Invoke-RestMethod -Method POST `
    -Uri "http://localhost:8000/api/v1/auth/refresh" `
    -Body (@{refresh_token=$response.refresh_token} | ConvertTo-Json) `
    -ContentType "application/json"
} catch {
  $_.Exception.Response.StatusCode -eq 401  # PASS — refresh token is revoked
}
```

---

## Validation Scenario 2: Full Case Lifecycle (US1 → US2)

### 2a. Upload documents and get AI field suggestions (FR-011 through FR-013)

Use `tests/fixtures/sample_clinical_note.pdf` — a native-text PDF containing "Member ID: M123456" and CPT "72148".

```powershell
$token = "<access_token>"

# Upload document
$uploadResult = curl -X POST "http://localhost:8000/api/v1/cases/upload-documents" `
  -H "Authorization: Bearer $token" `
  -F "files=@tests/fixtures/sample_clinical_note.pdf" | ConvertFrom-Json

# PASS checks
$uploadResult.extracted_fields.member_id.value -eq "M123456"   # FR-013
$uploadResult.extracted_fields.cpt_hcpcs_code.value -eq "72148"  # FR-013
$uploadResult.extracted_fields.member_id.ai_extracted -eq $true  # FR-014
$uploadResult.extracted_fields.icd10_code.value -eq $null        # FR-013: confident miss → null
```

### 2b. Create a policy first (required for case creation)

```powershell
# Upload policy PDF
$policyUpload = curl -X POST "http://localhost:8000/api/v1/policies/upload" `
  -H "Authorization: Bearer $token" `
  -F "file=@tests/fixtures/lumbar_spine_policy.pdf" `
  -F "name=Lumbar Spine MRI — 2026" | ConvertFrom-Json

# Wait for extraction to complete (poll draft-requirements)
$draft = curl "http://localhost:8000/api/v1/policies/$($policyUpload.policy_id)/draft-requirements" `
  -H "Authorization: Bearer $token" | ConvertFrom-Json

# PASS: at least one requirement extracted
$draft.draft_requirements.Count -gt 0

# Save requirements
$saveBody = @{ requirements = $draft.draft_requirements } | ConvertTo-Json -Depth 5
curl -X POST "http://localhost:8000/api/v1/policies/$($policyUpload.policy_id)/requirements" `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d $saveBody
```

### 2c. Submit case

```powershell
$caseBody = @{
  upload_session_id = $uploadResult.upload_session_id
  member_id = "M123456"
  requested_service = "MRI Lumbar Spine"
  cpt_hcpcs_code = "72148"
  policy_id = $policyUpload.policy_id
} | ConvertTo-Json

$case = curl -X POST "http://localhost:8000/api/v1/cases" `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d $caseBody | ConvertFrom-Json

# PASS: case created in processing state (FR-016)
$case.status -eq "processing"
```

### 2d. Poll until pipeline complete (FR-018, SC-003)

```powershell
$start = Get-Date
do {
  Start-Sleep 10
  $status = curl "http://localhost:8000/api/v1/cases/$($case.id)/status" `
    -H "Authorization: Bearer $token" | ConvertFrom-Json
  Write-Host "Status: $($status.status)"
} until ($status.status -ne "processing" -or (Get-Date) - $start -gt [TimeSpan]::FromMinutes(6))

# PASS: pipeline completes within 5 min (SC-003), status is pending_review
$status.status -eq "pending_review"
((Get-Date) - $start).TotalMinutes -lt 5
```

### 2e. Validate completeness report (FR-024, FR-035)

```powershell
$detail = curl "http://localhost:8000/api/v1/cases/$($case.id)" `
  -H "Authorization: Bearer $token" | ConvertFrom-Json

# PASS: verdicts are only present/absent/unclear, no raw scores (FR-024)
$detail.completeness_report | ForEach-Object {
  $_.verdict -in @("present","absent","unclear")
}

# PASS: case summary is non-empty (FR-035)
$detail.case_summary -ne $null -and $detail.case_summary.Length -gt 0
```

---

## Validation Scenario 3: Nurse Review Flow (US2 — FR-030 through FR-038)

```powershell
# Create nurse account via admin
$nurseBody = @{username="jnurse";full_name="Jane Nurse";password="NursePass1!";role="nurse"} | ConvertTo-Json
curl -X POST "http://localhost:8000/api/v1/admin/users" `
  -H "Authorization: Bearer $adminToken" `
  -H "Content-Type: application/json" -d $nurseBody

# Login as nurse
$nurseToken = (Invoke-RestMethod -Method POST `
  -Uri "http://localhost:8000/api/v1/auth/token" `
  -Body "username=jnurse&password=NursePass1!&grant_type=password" `
  -ContentType "application/x-www-form-urlencoded").access_token

# PASS: case appears in nurse queue (FR-030)
$queue = curl "http://localhost:8000/api/v1/nurse-review/queue" `
  -H "Authorization: Bearer $nurseToken" | ConvertFrom-Json
$queue.items | Where-Object { $_.id -eq $case.id }  # non-null

# Acquire lock (FR-031)
$lock = curl -X POST "http://localhost:8000/api/v1/nurse-review/cases/$($case.id)/lock" `
  -H "Authorization: Bearer $nurseToken" | ConvertFrom-Json
# PASS
$lock.locked -eq $true

# Heartbeat (FR-032)
$hb = curl -X POST "http://localhost:8000/api/v1/nurse-review/cases/$($case.id)/heartbeat" `
  -H "Authorization: Bearer $nurseToken" | ConvertFrom-Json
$hb.lock_last_active_at -ne $null  # PASS

# Decision: Accept (FR-037)
$decisionBody = @{decision="accepted";notes="Documentation is complete."} | ConvertTo-Json
$decision = curl -X POST "http://localhost:8000/api/v1/nurse-review/cases/$($case.id)/decision" `
  -H "Authorization: Bearer $nurseToken" `
  -H "Content-Type: application/json" -d $decisionBody | ConvertFrom-Json
# PASS
$decision.decision -eq "accepted"
```

---

## Validation Scenario 4: Admin Edit Re-Queue (US4 — FR-052 through FR-055)

```powershell
# Attempt edit without comment on decided case — must be blocked (FR-053)
try {
  curl -X PATCH "http://localhost:8000/api/v1/admin/cases/$($case.id)" `
    -H "Authorization: Bearer $adminToken" `
    -H "Content-Type: application/json" `
    -d '{"icd10_code":"M54.5"}' | ConvertFrom-Json
} catch {
  $_.Exception.Response.StatusCode -eq 422  # PASS
}

# Edit with mandatory comment
$editBody = @{icd10_code="M54.5"; admin_comment="Corrected ICD-10 per provider."} | ConvertTo-Json
$edited = curl -X PATCH "http://localhost:8000/api/v1/admin/cases/$($case.id)" `
  -H "Authorization: Bearer $adminToken" `
  -H "Content-Type: application/json" -d $editBody | ConvertFrom-Json

# PASS: case re-queued (FR-054)
$edited.status -eq "pending_review"
$edited.requeued -eq $true

# PASS: original acceptance in history (FR-055)
$history = curl "http://localhost:8000/api/v1/admin/cases/$($case.id)/history" `
  -H "Authorization: Bearer $adminToken" | ConvertFrom-Json
$history.history | Where-Object { $_.decision -eq "accepted" }  # non-null
```

---

## Validation Scenario 5: Constitution Compliance Smoke Tests

```powershell
# SC-010: Unauthenticated requests return 401 within 200ms
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try { Invoke-RestMethod "http://localhost:8000/api/v1/cases" } catch {}
$sw.Stop()
$sw.ElapsedMilliseconds -lt 200  # PASS

# Nurse role cannot access admin audit log (FR-003)
try {
  curl "http://localhost:8000/api/v1/admin/audit-log" `
    -H "Authorization: Bearer $nurseToken" | ConvertFrom-Json
} catch {
  $_.Exception.Response.StatusCode -eq 403  # PASS
}

# Intake role cannot upload a policy (FR-040)
# (Create intake user first, get intake token)
# ... similar pattern — expected 403
```

---

## Expected Outcomes Summary

| Scenario | Key Assertions | Spec References |
|---|---|---|
| Auth | Login returns JWT + refresh; unauthenticated → 401 < 200ms; logout revokes refresh | FR-001–006, SC-010 |
| Document upload | AI pre-fills member_id + CPT; leaves ICD-10 null when not found | FR-011–014 |
| Case create | Returns 202 immediately, status = "processing" | FR-016 |
| Pipeline | Completes within 5 min, status = "pending_review" | SC-003, FR-020–025 |
| Completeness report | Only present/absent/unclear verdicts; OCR evidence tagged | FR-024, FR-035, SC-008 |
| Nurse lock | Exclusive acquire succeeds; heartbeat extends; 409 on concurrent acquire | FR-031–032, SC-005 |
| Nurse decision | Accept moves case to decided; lock released | FR-037 |
| Admin edit | 422 without comment; 200+requeued with comment; original decision in history | FR-052–055, SC-007 |
| Role enforcement | Nurse → 403 on audit log; intake → 403 on policy upload | FR-003, FR-040 |

---

## Fixture Files

Place under `backend/tests/fixtures/`:
- `sample_clinical_note.pdf` — native-text PDF, 2 pages, contains "Member ID: M123456", CPT "72148", service "MRI Lumbar Spine"
- `sample_scanned_fax.pdf` — image-only PDF (single scanned page) — triggers OCR path
- `lumbar_spine_policy.pdf` — policy document with at least 3 extractable requirements

Generating test fixtures: use any PDF library or a real de-identified document. The content only needs to be plausible plain text — the LLM's extraction pass is what's being validated, not specific clinical accuracy.
