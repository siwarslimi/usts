"""Sending replies exactly once.

* The client generates an Idempotency-Key per composed reply. Double clicks and
  network retries reuse it, and the UNIQUE constraint turns them into a no-op.
* "Réessayer" is only possible from the `failed` state and is a conditional
  UPDATE (failed -> sending), so two concurrent retries cannot both win.
* The send itself is delegated to n8n (never called by the site), which reports
  the final status back through a signed webhook.
"""
import json
import logging
import time
from datetime import timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import Email, SentReply, utcnow
from ..security import SECRET_HEADER, SIGNATURE_HEADER, sign_body
from . import events

log = logging.getLogger("replies")

SENDING_TIMEOUT = timedelta(minutes=10)
MOCK_FAILURE_MARKER = "[test-echec]"


def create_reply(db: Session, email: Email, body: str, draft_id: int | None, key: str) -> tuple[SentReply, bool]:
    existing = db.scalar(select(SentReply).where(SentReply.idempotency_key == key))
    if existing:
        return existing, False
    reply = SentReply(email_id=email.id, draft_id=draft_id, idempotency_key=key, body=body, status="sending")
    db.add(reply)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.scalar(select(SentReply).where(SentReply.idempotency_key == key)), False
    events.publish("reply", {"reply_id": reply.id, "email_id": email.id, "status": "sending"})
    return reply, True


def claim_retry(db: Session, reply_id: int) -> bool:
    res = db.execute(
        update(SentReply)
        .where(SentReply.id == reply_id, SentReply.status == "failed")
        .values(status="sending", error=None, attempts=SentReply.attempts + 1, updated_at=utcnow())
    )
    db.commit()
    return res.rowcount == 1


def expire_stuck(db: Session, replies: list[SentReply]) -> None:
    now = utcnow()
    changed = False
    for r in replies:
        if r.status == "sending" and now - r.updated_at > SENDING_TIMEOUT:
            r.status = "failed"
            r.error = "Aucune confirmation d'envoi reçue (délai dépassé)"
            changed = True
    if changed:
        db.commit()


def record_status(db: Session, reply: SentReply, status: str, gmail_message_id: str | None, error: str | None) -> None:
    if reply.status == "sent":
        return  # already final: a late or duplicated callback changes nothing
    reply.status = status
    reply.error = None if status == "sent" else (error or "Échec de l'envoi")
    if status == "sent":
        reply.gmail_message_id = gmail_message_id
        reply.sent_at = utcnow()
        email = db.get(Email, reply.email_id)
        email.status = "replied"
        email.thread.last_message_at = reply.sent_at
    db.commit()
    events.publish("reply", {"reply_id": reply.id, "email_id": reply.email_id, "status": status})


def _n8n_payload(email: Email, reply: SentReply) -> dict:
    subject = email.subject or ""
    if not subject.lower().startswith(("re:", "re :")):
        subject = f"Re: {subject}"
    references = " ".join(x for x in [email.references or "", email.rfc_message_id or ""] if x).strip()
    return {
        "reply_id": reply.id,
        "gmail_thread_id": email.thread.gmail_thread_id,
        "to": email.from_email,
        "subject": subject,
        "in_reply_to": email.rfc_message_id,
        "references": references or None,
        "body": reply.body,
    }


def dispatch(reply_id: int) -> None:
    """Runs as a background task, with its own DB session."""
    s = get_settings()
    db = SessionLocal()
    try:
        reply = db.get(SentReply, reply_id)
        if reply is None or reply.status != "sending":
            return
        email = db.get(Email, reply.email_id)

        if s.reply_transport == "mock":
            time.sleep(1.5)
            if MOCK_FAILURE_MARKER in reply.body and reply.attempts == 1:
                record_status(db, reply, "failed", None, "Échec simulé (mode démo)")
            else:
                record_status(db, reply, "sent", f"mock-{reply.id}", None)
            return

        # Compact separators: n8n re-serializes the parsed body with JSON.stringify to check the HMAC
        body = json.dumps(_n8n_payload(email, reply), ensure_ascii=False, separators=(",", ":")).encode()
        headers = {
            "Content-Type": "application/json",
            SECRET_HEADER: s.webhook_secret,
            SIGNATURE_HEADER: sign_body(body, s.webhook_secret),
        }
        try:
            r = httpx.post(s.n8n_send_webhook_url, content=body, headers=headers, timeout=15)
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("Reply %s: n8n dispatch failed (%s)", reply.id, type(e).__name__)
            record_status(db, reply, "failed", None, "Service d'envoi (n8n) injoignable")
    finally:
        db.close()
