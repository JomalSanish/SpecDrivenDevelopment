"""
backend/src/api/schemas.py

Pydantic request/response schemas for all Phase 2 routes.
Keeps ORM models separate from API surface.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Policy schemas
# ---------------------------------------------------------------------------


class PolicyRequirementOut(BaseModel):
    id: uuid.UUID
    description: str
    matching_criteria: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class PolicyOut(BaseModel):
    id: uuid.UUID
    title: str
    service_line_code: str
    version: str
    active: bool
    sla_hours: int | None = None
    created_at: datetime
    requirements: list[PolicyRequirementOut] = []

    model_config = {"from_attributes": True}


class PolicyIngestResponse(BaseModel):
    policy_id: uuid.UUID
    title: str
    service_line_code: str
    version: str
    requirements: list[PolicyRequirementOut]


# ---------------------------------------------------------------------------
# Case schemas
# ---------------------------------------------------------------------------


class CaseCreateRequest(BaseModel):
    member_id: str = Field(..., min_length=1, max_length=128)
    provider_id: str = Field(..., min_length=1, max_length=128)
    cpt_code: str = Field(..., min_length=1, max_length=16)
    icd10_code: str = Field(..., min_length=1, max_length=16)
    service_type: str = Field(..., min_length=1, max_length=128)
    requested_date: datetime
    policy_id: uuid.UUID


class DocumentOut(BaseModel):
    id: uuid.UUID
    document_type: str
    storage_path: str
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class CaseCreateResponse(BaseModel):
    case_id: uuid.UUID
    status: str  # "pending_verification"


class CaseOut(BaseModel):
    id: uuid.UUID
    member_id: str
    provider_id: str
    cpt_code: str
    icd10_code: str
    service_type: str
    requested_date: datetime
    policy_id: uuid.UUID
    review_status: str
    assigned_queue: str
    claimed_by_id: uuid.UUID | None = None
    entered_review_at: datetime | None = None
    decided_by_id: uuid.UUID | None = None
    decision_reason: str | None = None
    decision_at: datetime | None = None
    created_at: datetime
    documents: list[DocumentOut] = []

    model_config = {"from_attributes": True}
