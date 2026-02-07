"""SQLAlchemy database engine, session, and ORM models for D.E.S."""

import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Boolean,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/des")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def _uuid():
    return uuid.uuid4()


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    filename = Column(Text, nullable=False)
    source = Column(String(20), nullable=False, default="upload")  # upload | dotloop | docusign
    source_id = Column(Text, nullable=True)  # external ID (loop_id, envelope_id)
    mode = Column(String(20), nullable=False)  # real_estate | gov
    page_count = Column(Integer, nullable=False, default=0)
    file_size_bytes = Column(Integer, nullable=False, default=0)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    extractions = relationship("Extraction", back_populates="document", cascade="all, delete-orphan")


class Extraction(Base):
    __tablename__ = "extractions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    engine = Column(String(20), nullable=False, default="openai")  # openai | local
    model_used = Column(Text, nullable=False, default="docextract-vision-v1")
    mode = Column(String(20), nullable=False)
    extracted_data = Column(JSONB, nullable=True)
    dotloop_api_payload = Column(JSONB, nullable=True)
    validation_success = Column(Boolean, nullable=False, default=True)
    validation_errors = Column(JSONB, nullable=True)
    overall_confidence = Column(Float, nullable=False, default=0.0)
    pages_processed = Column(Integer, nullable=False, default=0)
    extraction_timestamp = Column(DateTime(timezone=True), nullable=False, default=_now)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    document = relationship("Document", back_populates="extractions")
    citations = relationship("Citation", back_populates="extraction", cascade="all, delete-orphan")
    pii_findings = relationship("PIIFindingRow", back_populates="extraction", cascade="all, delete-orphan")
    pii_report = relationship("PIIReportRow", back_populates="extraction", uselist=False, cascade="all, delete-orphan")


class Citation(Base):
    __tablename__ = "citations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    extraction_id = Column(UUID(as_uuid=True), ForeignKey("extractions.id"), nullable=False)
    field_name = Column(Text, nullable=False)
    extracted_value = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=False)
    line_or_region = Column(Text, nullable=False)
    surrounding_text = Column(Text, nullable=False, default="")
    confidence = Column(Float, nullable=False, default=0.0)

    extraction = relationship("Extraction", back_populates="citations")


class PIIFindingRow(Base):
    __tablename__ = "pii_findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    extraction_id = Column(UUID(as_uuid=True), ForeignKey("extractions.id"), nullable=False)
    pii_type = Column(String(10), nullable=False)  # SSN | PHONE | EMAIL
    value_redacted = Column(Text, nullable=False)
    severity = Column(String(10), nullable=False)  # HIGH | MEDIUM | LOW
    confidence = Column(Float, nullable=False, default=0.0)
    location = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=False, default="")

    extraction = relationship("Extraction", back_populates="pii_findings")


class PIIReportRow(Base):
    __tablename__ = "pii_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    extraction_id = Column(UUID(as_uuid=True), ForeignKey("extractions.id"), nullable=False, unique=True)
    risk_score = Column(Integer, nullable=False, default=0)
    risk_level = Column(String(10), nullable=False, default="LOW")
    finding_count = Column(Integer, nullable=False, default=0)

    extraction = relationship("Extraction", back_populates="pii_report")
