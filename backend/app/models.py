from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def utcnow(): return datetime.now(timezone.utc)

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    required_skills: Mapped[list] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSON, default=list)
    min_years: Mapped[float] = mapped_column(Float, default=0)
    domain_keywords: Mapped[list] = mapped_column(JSON, default=list)
    education_keywords: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="job", cascade="all, delete-orphan")

class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="Candidate")
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="incomplete")
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fit_band: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevant_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_coverage: Mapped[float] = mapped_column(Float, default=0)
    criterion_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    weights_used: Mapped[dict] = mapped_column(JSON, default=dict)
    verified_skills: Mapped[list] = mapped_column(JSON, default=list)
    unverified_skills: Mapped[list] = mapped_column(JSON, default=list)
    confirmed_absent_skills: Mapped[list] = mapped_column(JSON, default=list)
    criterion_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    criterion_gaps: Mapped[dict] = mapped_column(JSON, default=dict)
    projects: Mapped[list] = mapped_column(JSON, default=list)
    evidence_summary: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(40), default="Pending review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    job: Mapped[Job] = relationship(back_populates="candidates")

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
