"""
SQLAlchemy Async ORM Database Models for cerberus</>.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def generate_uuid() -> str:
    return str(uuid.uuid4())


class CodeReviewRecord(Base):
    __tablename__ = "code_reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    github_pr_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    github_repo_owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    github_repo_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    commit_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    code_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(50), default="python")
    status: Mapped[str] = mapped_column(String(20), default="processing")  # processing, completed, failed, approved
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    results_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    findings: Mapped[List["FindingRecord"]] = relationship(
        "FindingRecord", back_populates="review", cascade="all, delete-orphan"
    )
    feedback: Mapped[Optional["ReviewFeedbackRecord"]] = relationship(
        "ReviewFeedbackRecord", back_populates="review", uselist=False
    )


class FindingRecord(Base):
    __tablename__ = "review_findings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    review_id: Mapped[str] = mapped_column(String(64), ForeignKey("code_reviews.id"), index=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    line_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    column_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    code_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remediation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggestion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cwe_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    cvss_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exploitability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    false_positive_probability: Mapped[float] = mapped_column(Float, default=0.02)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    review: Mapped["CodeReviewRecord"] = relationship("CodeReviewRecord", back_populates="findings")


class ReviewFeedbackRecord(Base):
    __tablename__ = "review_feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    review_id: Mapped[str] = mapped_column(String(64), ForeignKey("code_reviews.id"), unique=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    is_helpful: Mapped[bool] = mapped_column(Boolean, default=True)
    false_positives: Mapped[int] = mapped_column(Integer, default=0)
    false_negatives: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    review: Mapped["CodeReviewRecord"] = relationship("CodeReviewRecord", back_populates="feedback")


class ApiKeyRecord(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, default="default", index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[Optional[str]] = mapped_column(String(255), default="review:read,review:write")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RuntimeConfigRecord(Base):
    __tablename__ = "runtime_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
