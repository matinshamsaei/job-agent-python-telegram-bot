from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    current_title: Mapped[str] = mapped_column(String(200))
    years_experience: Mapped[int] = mapped_column(Integer)
    skills: Mapped[list] = mapped_column(JSONB, default=list)
    target_roles: Mapped[list] = mapped_column(JSONB, default=list)
    target_countries: Mapped[list] = mapped_column(JSONB, default=list)
    preferred_countries: Mapped[list] = mapped_column(JSONB, default=list)
    visa_required: Mapped[bool] = mapped_column(Boolean, default=True)
    relocation_required: Mapped[bool] = mapped_column(Boolean, default=True)
    english_level: Mapped[str] = mapped_column(String(50), default="professional")
    salary_preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    additional_preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    resumes: Mapped[list["CandidateResume"]] = relationship(back_populates="profile")


class CandidateResume(Base):
    __tablename__ = "candidate_resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), index=True)
    variant: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    skills: Mapped[list] = mapped_column(JSONB, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    profile: Mapped[CandidateProfile] = relationship(back_populates="resumes")


class TargetCompany(Base):
    __tablename__ = "target_companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(2), index=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ats_type: Mapped[str] = mapped_column(String(40), default="unknown")
    board_token: Mapped[str | None] = mapped_column(String(200), nullable=True)
    careers_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    visa_status: Mapped[str] = mapped_column(String(20), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    aliases: Mapped[list["CompanyAlias"]] = relationship(back_populates="company")
    evidence: Mapped[list["CompanyEvidence"]] = relationship(back_populates="company")
    jobs: Mapped[list["Job"]] = relationship(back_populates="company")


class CompanyAlias(Base):
    __tablename__ = "company_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("target_companies.id"), index=True)
    alias: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped[TargetCompany] = relationship(back_populates="aliases")

    __table_args__ = (UniqueConstraint("company_id", "alias", name="uq_company_alias"),)


class CompanyEvidence(Base):
    __tablename__ = "company_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("target_companies.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    claim: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped[TargetCompany] = relationship(back_populates="evidence")


class JobSource(Base):
    __tablename__ = "job_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("target_companies.id"), index=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    external_id: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(400))
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    remote_type: Mapped[str] = mapped_column(String(20), default="unknown")
    employment_type: Mapped[str] = mapped_column(String(30), default="unknown")
    description: Mapped[str] = mapped_column(Text, default="")
    description_hash: Mapped[str] = mapped_column(String(64), index=True)
    salary: Mapped[str | None] = mapped_column(String(200), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str] = mapped_column(String(1000))
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped[TargetCompany] = relationship(back_populates="jobs")
    analysis: Mapped["JobAnalysis | None"] = relationship(back_populates="job", uselist=False)
    score: Mapped["JobScore | None"] = relationship(back_populates="job", uselist=False)
    decisions: Mapped[list["JobDecision"]] = relationship(back_populates="job")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="job")

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_job_source_external_id"),)


class JobAnalysis(Base):
    __tablename__ = "job_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True, index=True)
    role_category: Mapped[str] = mapped_column(String(40), default="unknown")
    seniority: Mapped[str] = mapped_column(String(40), default="unknown")
    years_required: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_skills: Mapped[list] = mapped_column(JSONB, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSONB, default=list)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    remote_type: Mapped[str] = mapped_column(String(20), default="unknown")
    visa_status: Mapped[str] = mapped_column(String(20), default="unknown")
    relocation_status: Mapped[str] = mapped_column(String(20), default="unknown")
    salary: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(30), default="unknown")
    positive_signals: Mapped[list] = mapped_column(JSONB, default=list)
    red_flags: Mapped[list] = mapped_column(JSONB, default=list)
    description_hash: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="analysis")


class JobScore(Base):
    __tablename__ = "job_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True, index=True)
    overall_score: Mapped[float] = mapped_column(Float)
    breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)
    positive_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    negative_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    risks: Mapped[list] = mapped_column(JSONB, default=list)
    recommendation: Mapped[str] = mapped_column(String(20))
    weights: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="score")


class JobDecision(Base):
    __tablename__ = "job_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    decision: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_features: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="decisions")


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("target_companies.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="intended")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resume_variant: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cover_letter_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    application_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    events: Mapped[list["ApplicationEvent"]] = relationship(back_populates="application")


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped[Application] = relationship(back_populates="events")


class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    candidate_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_resumes.id"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    channel: Mapped[str] = mapped_column(String(40), default="telegram")
    status: Mapped[str] = mapped_column(String(20), default="sent")
    external_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="notifications")


class LearningFeedback(Base):
    __tablename__ = "learning_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    job_features: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SearchRun(Base):
    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(80), default="run_once")
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_created: Mapped[int] = mapped_column(Integer, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0)
    jobs_skipped: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VerificationRun(Base):
    __tablename__ = "verification_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(80), default="manual")
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_created: Mapped[int] = mapped_column(Integer, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0)
    jobs_skipped: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
