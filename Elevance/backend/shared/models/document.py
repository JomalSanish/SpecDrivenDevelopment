from sqlalchemy import Column, String, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
import enum
import uuid
from pgvector.sqlalchemy import Vector
from shared.db import Base

class DocumentType(str, enum.Enum):
    CLINICAL_NOTE = "clinical_note"
    REFERRAL_FORM = "referral_form"
    ATTACHMENT = "attachment"
    MEDICAL_POLICY = "medical_policy"
    BENEFIT_PLAN = "benefit_plan"

class Document(Base):
    __tablename__ = "documents"

    document_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=False)
    type = Column(Enum(DocumentType), nullable=False)
    source = Column(String, nullable=False)
    parsed_text = Column(Text, nullable=True)
    embedding_refs = Column(ARRAY(UUID(as_uuid=True)), default=[])

    case = relationship("Case", back_populates="documents")


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    policy_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section = Column(String, nullable=False)
    text_chunks = Column(ARRAY(Text), default=[])
    # pgvector embedding representation, assume 1536 dim for typical OpenAI or matching Claude setups
    embeddings = Column(Vector(1536))
    version = Column(String, nullable=False)
