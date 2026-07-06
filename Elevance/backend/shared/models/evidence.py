from sqlalchemy import Column, String, Float, Enum, ForeignKey, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
import enum
import uuid
from datetime import datetime, timezone
from shared.db import Base

class GapStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    UNCLEAR = "unclear"

class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    evidence_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False)
    source = Column(String, nullable=False)
    matched_text = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    citation_ref = Column(UUID(as_uuid=True), nullable=True)

    case = relationship("Case", back_populates="evidence_items")

class GapChecklistItem(Base):
    __tablename__ = "gap_checklist_items"

    checklist_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False)
    criterion = Column(Text, nullable=False)
    status = Column(Enum(GapStatus), nullable=False)
    rationale = Column(Text, nullable=False)
    evidence_refs = Column(ARRAY(UUID(as_uuid=True)), default=[])

    case = relationship("Case", back_populates="gap_checklist")

class AuditLogEntry(Base):
    __tablename__ = "audit_logs"

    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False)
    agent = Column(String, nullable=False)
    action = Column(String, nullable=False)
    input_hash = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    model_version = Column(String, nullable=False)
    sources = Column(ARRAY(UUID(as_uuid=True)), default=[])
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Note: case relationship for query convenience
    # For a partitioned table, typical foreign key constraints from partitioned tables to other tables 
    # are supported in newer Postgres, but often avoided for pure append-only logs. We include it here.
