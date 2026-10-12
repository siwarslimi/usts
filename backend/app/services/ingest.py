import re
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Email, Thread
from ..schemas import IncomingEmail

WS_RE = re.compile(r"\s+")
NUL = chr(0)
INGEST_LOCK_ID = 7_201_337  # arbitrary key for pg_advisory_xact_lock


def _snippet(text: str) -> str:
    return WS_RE.sub(" ", text).strip()[:200]


def _to_utc_naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _clean(value: str | None, max_len: int | None = None) -> str:
    """PostgreSQL rejects NUL characters; column sizes are bounded."""
    value = (value or "").replace(NUL, "")
    return value[:max_len] if max_len else value


def _thread_for(db: Session, item: IncomingEmail, received: datetime) -> Thread:
    thread = db.scalar(select(Thread).where(Thread.gmail_thread_id == item.gmail_thread_id))
    if thread is None:
        sp = db.begin_nested()
        try:
            thread = Thread(gmail_thread_id=item.gmail_thread_id, subject=_clean(item.subject, 998), last_message_at=received)
            db.add(thread)
            db.flush()
            sp.commit()
        except IntegrityError:  # created meanwhile by another import
            sp.rollback()
            thread = db.scalar(select(Thread).where(Thread.gmail_thread_id == item.gmail_thread_id))
    elif received > thread.last_message_at:
        thread.last_message_at = received
    return thread


def ingest_emails(db: Session, items: list[IncomingEmail], run_id: int | None) -> tuple[dict[str, int], int]:
    """Insert new messages; a Gmail message id already known is silently skipped.

    The UNIQUE constraint on gmail_message_id is the real guarantee: even two
    concurrent imports of the same message end up with a single row. On
    PostgreSQL, imports are also serialized with a transaction-level advisory
    lock, so parallel batches touching the same threads cannot deadlock.
    """
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": INGEST_LOCK_ID})

    new_ids: dict[str, int] = {}
    duplicates = 0
    seen_in_batch: set[str] = set()

    for item in sorted(items, key=lambda i: _to_utc_naive(i.received_at)):
        if item.gmail_message_id in seen_in_batch:
            duplicates += 1
            continue
        seen_in_batch.add(item.gmail_message_id)

        if db.scalar(select(Email.id).where(Email.gmail_message_id == item.gmail_message_id)):
            duplicates += 1
            continue

        received = _to_utc_naive(item.received_at)
        thread = _thread_for(db, item, received)
        savepoint = db.begin_nested()
        try:
            body = _clean(item.body_text)
            email = Email(
                gmail_message_id=item.gmail_message_id,
                thread_id=thread.id,
                sync_run_id=run_id,
                from_name=_clean(item.from_name, 255).strip(),
                from_email=_clean(item.from_email, 255).strip().lower(),
                to=[_clean(a, 255) for a in item.to],
                cc=[_clean(a, 255) for a in item.cc],
                subject=_clean(item.subject, 998),
                body_text=body,
                snippet=_snippet(body),
                received_at=received,
                rfc_message_id=_clean(item.rfc_message_id, 998) or None,
                references=_clean(item.references) or None,
            )
            db.add(email)
            db.flush()
            savepoint.commit()
            new_ids[item.gmail_message_id] = email.id
        except IntegrityError:
            savepoint.rollback()
            duplicates += 1

    db.commit()
    return new_ids, duplicates
