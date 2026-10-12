from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

CATEGORIES = ("client", "facture", "rendez-vous", "newsletter", "spam probable", "autre")
STATUSES = ("to_process", "draft_ready", "replied", "ignored")
TONES = ("formel", "neutre", "court")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    gmail_thread_id: Mapped[str] = mapped_column(String(64), unique=True)
    subject: Mapped[str] = mapped_column(String(998), default="")
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    emails: Mapped[list["Email"]] = relationship(back_populates="thread", order_by="Email.received_at")


class Email(Base):
    __tablename__ = "emails"
    __table_args__ = (
        Index("ix_emails_received_at", "received_at"),
        Index("ix_emails_status", "status"),
        Index("ix_emails_category", "category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Idempotency key for imports: a Gmail message is stored once, whatever happens
    gmail_message_id: Mapped[str] = mapped_column(String(64), unique=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id"))
    sync_run_id: Mapped[int | None] = mapped_column(ForeignKey("sync_runs.id"), nullable=True)

    from_name: Mapped[str] = mapped_column(String(255), default="")
    from_email: Mapped[str] = mapped_column(String(255), index=True)
    to: Mapped[list] = mapped_column(JSON, default=list)
    cc: Mapped[list] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(String(998), default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(String(300), default="")
    received_at: Mapped[datetime] = mapped_column(DateTime)
    rfc_message_id: Mapped[str | None] = mapped_column(String(998), nullable=True)
    references: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI classification
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expected_action: Mapped[str | None] = mapped_column(String(300), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    classification_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|done|review
    classification_attempts: Mapped[int] = mapped_column(Integer, default=0)
    classification_first_try_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="to_process")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    thread: Mapped[Thread] = relationship(back_populates="emails")
    drafts: Mapped[list["Draft"]] = relationship(back_populates="email", order_by="Draft.created_at")
    replies: Mapped[list["SentReply"]] = relationship(back_populates="email", order_by="SentReply.created_at")


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), index=True)
    tone: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))  # ai | template
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    email: Mapped[Email] = relationship(back_populates="drafts")


class SentReply(Base):
    __tablename__ = "sent_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), index=True)
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("drafts.id"), nullable=True)
    # Idempotency key for sending: one key == at most one email sent
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="sending")  # sending|sent|failed
    gmail_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    email: Mapped[Email] = relationship(back_populates="replies")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16), default="gmail")  # gmail | demo
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|success|failed
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Gmail "after:" cursor (epoch seconds) used by this run and the one to use next time
    cursor_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cursor_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class WorkflowError(Base):
    __tablename__ = "workflow_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow: Mapped[str] = mapped_column(String(255))
    node: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(String(1000))
    execution_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
