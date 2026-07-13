"""
backend/src/api/intake_routes.py

Case Intake routes.

POST /api/v1/intake/cases
  Accepts case metadata (JSON body) + one or more document files (multipart).
  Creates a Case and Document records in PostgreSQL.
  Stores each document in MinIO.
  Returns { case_id, status: "pending_verification" }.

Contract: api.md §Intake Routes (FR-002)
Constitution: §II (local storage only — MinIO), §I (explicit state fields),
              §V (secrets abstraction for MinIO credentials).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, BackgroundTasks
from fastapi import Body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import CaseCreateResponse, CaseOut, DocumentOut
from src.core.database import get_db
from src.core.storage import upload_document
from src.models.case import Case, Document, DocumentType, ReviewStatus, AssignedQueue
from src.models.policy import Policy
from src.services.completeness_pipeline import run_completeness_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/intake", tags=["Intake"])

# Allowed MIME types for case document uploads
_ALLOWED_TYPES = {
    "application/pdf": DocumentType.pdf,
    "image/tiff": DocumentType.scan,
    "image/png": DocumentType.scan,
    "image/jpeg": DocumentType.scan,
    "application/octet-stream": DocumentType.fax,  # raw fax stream
}


@router.post(
    "/cases",
    response_model=CaseCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new prior authorization case with evidence documents",
    description=(
        "Submit case metadata and one or more evidence documents (PDFs, scans, faxes). "
        "Documents are stored in local MinIO — no external egress (Constitution §II). "
        "Case enters 'pending_verification' status until the completeness pipeline runs."
    ),
)
async def create_case(
    background_tasks: BackgroundTasks,
    member_id: str = Form(..., description="Member / patient ID"),
    provider_id: str = Form(..., description="Ordering provider ID"),
    cpt_code: str = Form(..., description="Requested procedure CPT code"),
    icd10_code: str = Form(..., description="Primary diagnosis ICD-10 code"),
    service_type: str = Form(..., description="Service type description"),
    requested_date: datetime = Form(..., description="Date of service request (ISO 8601)"),
    policy_id: uuid.UUID = Form(..., description="Policy UUID to evaluate against"),
    documents: list[UploadFile] = File(..., description="One or more evidence documents"),
    db: AsyncSession = Depends(get_db),
) -> CaseCreateResponse:
    # ----------------------------------------------------------------
    # 1. Verify the referenced policy exists and is active
    # ----------------------------------------------------------------
    stmt = select(Policy).where(Policy.id == policy_id, Policy.active.is_(True))
    result = await db.execute(stmt)
    policy = result.scalar_one_or_none()
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active policy found with id={policy_id}.",
        )

    # ----------------------------------------------------------------
    # 2. Validate uploads
    # ----------------------------------------------------------------
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one evidence document must be uploaded.",
        )

    # ----------------------------------------------------------------
    # 3. Create Case row (explicit state — constitution §I)
    # ----------------------------------------------------------------
    case = Case(
        member_id=member_id,
        provider_id=provider_id,
        cpt_code=cpt_code,
        icd10_code=icd10_code,
        service_type=service_type,
        requested_date=requested_date,
        policy_id=policy_id,
        review_status=ReviewStatus.pending_verification,
        assigned_queue=AssignedQueue.nurse_review,
        claimed_by_id=None,
        entered_review_at=None,
    )
    db.add(case)
    await db.flush()  # get case.id

    # ----------------------------------------------------------------
    # 4. Upload each document to MinIO + create Document rows
    # ----------------------------------------------------------------
    for upload in documents:
        content_type = upload.content_type or "application/octet-stream"
        doc_type = _ALLOWED_TYPES.get(content_type, DocumentType.pdf)

        file_bytes = await upload.read()
        if len(file_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Uploaded file '{upload.filename}' is empty.",
            )

        # Object key: <case_id>/<document_uuid>/<filename>
        doc_id = uuid.uuid4()
        safe_name = (upload.filename or "document").replace(" ", "_")
        object_key = f"{case.id}/{doc_id}/{safe_name}"

        try:
            upload_document(object_key, file_bytes, content_type=content_type)
        except Exception as exc:
            logger.error("MinIO upload failed for case %s: %s", case.id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Document storage is unavailable. "
                    "Is MinIO running? (docker-compose up -d minio)"
                ),
            ) from exc

        doc = Document(
            id=doc_id,
            case_id=case.id,
            document_type=doc_type,
            storage_path=object_key,
        )
        db.add(doc)

    await db.commit()

    logger.info(
        "Case created: id=%s member=%s policy=%s docs=%d — scheduling completeness pipeline",
        case.id,
        member_id,
        policy_id,
        len(documents),
    )

    # Kick off the completeness pipeline in the background.
    # The HTTP 201 is returned immediately; the case advances to
    # in_nurse_review once pipeline completes (FR-004).
    background_tasks.add_task(run_completeness_pipeline, str(case.id))

    return CaseCreateResponse(
        case_id=case.id,
        status=ReviewStatus.pending_verification.value,
    )


@router.get(
    "/cases/{case_id}",
    response_model=CaseOut,
    summary="Retrieve a case with its documents",
)
async def get_case(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CaseOut:
    stmt = select(Case).where(Case.id == case_id)
    result = await db.execute(stmt)
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")

    stmt_docs = select(Document).where(Document.case_id == case_id)
    docs_result = await db.execute(stmt_docs)
    docs = docs_result.scalars().all()

    return CaseOut(
        id=case.id,
        member_id=case.member_id,
        provider_id=case.provider_id,
        cpt_code=case.cpt_code,
        icd10_code=case.icd10_code,
        service_type=case.service_type,
        requested_date=case.requested_date,
        policy_id=case.policy_id,
        review_status=case.review_status.value,
        assigned_queue=case.assigned_queue.value,
        claimed_by_id=case.claimed_by_id,
        entered_review_at=case.entered_review_at,
        decided_by_id=case.decided_by_id,
        decision_reason=case.decision_reason,
        decision_at=case.decision_at,
        created_at=case.created_at,
        documents=[
            DocumentOut(
                id=d.id,
                document_type=d.document_type.value,
                storage_path=d.storage_path,
                uploaded_at=d.uploaded_at,
            )
            for d in docs
        ],
    )
