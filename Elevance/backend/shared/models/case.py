from sqlalchemy import Column, String, Float, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
import enum
import uuid
from datetime import datetime, timezone
from shared.db import Base

class CaseStatus(str, enum.Enum):
    CREATED = "Created"
    INTAKE_REVIEW = "Intake Review"
    READY_FOR_EVIDENCE_REVIEW = "Ready for Evidence Review"
    NURSE_REVIEW = "Nurse Review"
    MEDICAL_DIRECTOR_REVIEW = "Medical Director Review"
    AWAITING_PROVIDER_DOCUMENTATION = "Awaiting Provider Documentation"

class RequestType(str, enum.Enum):
    IMAGING = "imaging"
    SURGERY = "surgery"
    DRUG = "drug"
    DME = "DME"
    BEHAVIORAL_HEALTH = "behavioral health"
    SPECIALTY_REFERRAL = "specialty referral"

class QueueType(str, enum.Enum):
    INTAKE = "Intake"
    NURSE_REVIEW = "Nurse Review"
    MEDICAL_DIRECTOR_REVIEW = "Medical Director Review"

class Case(Base):
    __tablename__ = "cases"

    case_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(String, nullable=False)
    provider_id = Column(String, nullable=False)
    request_type = Column(Enum(RequestType), nullable=False)
    cpt_hcpcs_codes = Column(ARRAY(String), default=[])
    icd_10_codes = Column(ARRAY(String), default=[])
    status = Column(Enum(CaseStatus), nullable=False, default=CaseStatus.CREATED)
    routing_confidence_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    routing_decision = relationship("RoutingDecision", back_populates="case", uselist=False, cascade="all, delete-orphan")
    evidence_items = relationship("EvidenceItem", back_populates="case", cascade="all, delete-orphan")
    gap_checklist = relationship("GapChecklistItem", back_populates="case", cascade="all, delete-orphan")


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"

    routing_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False)
    queue = Column(Enum(QueueType), nullable=False)
    reason = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)

    case = relationship("Case", back_populates="routing_decision")
