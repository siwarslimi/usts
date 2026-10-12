"""Endpoints called by n8n only. Protected by a shared secret header (+ optional HMAC)."""
import logging
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Email, SentReply, SyncRun, WorkflowError, utcnow
from ..schemas import (
    ClassificationIn,
    ClassificationOut,
    IngestIn,
    IngestOut,
    KnownIdsIn,
    KnownIdsOut,
    PendingClassification,
    ReplyStatusIn,
    SyncFinishIn,
    SyncStartIn,
    SyncStartOut,
    WorkflowErrorIn,
)
from ..security import verify_webhook
from ..services import events, replies
from ..services.classification import MAX_ATTEMPTS, apply_classification
from ..services.ingest import ingest_emails
from ..services.masking import mask_sensitive

log = logging.getLogger("webhooks")
router = APIRouter(prefix="/webhooks/n8n", tags=["webhooks n8n"], dependencies=[Depends(verify_webhook)])

CURSOR_OVERLAP_S = 300  # re-read 5 minutes of history: duplicates are absorbed by idempotency
# Primary tab only (no promotions / social), and a short first window to protect the AI quota
BASE_QUERY = "in:inbox category:primary"
INITIAL_QUERY = f"{BASE_QUERY} newer_than:2d"


@router.post("/sync-runs", response_model=SyncStartOut, summary="Démarrer une synchronisation, renvoie le curseur")
def start_sync(data: SyncStartIn, db: Session = Depends(get_db)):
    last_ok = db.scalar(
        select(SyncRun)
        .where(SyncRun.status == "success", SyncRun.source == "gmail", SyncRun.cursor_after.is_not(None))
        .order_by(SyncRun.id.desc())
        .limit(1)
    )
    after = (last_ok.cursor_after - CURSOR_OVERLAP_S) if last_ok else None
    # A run that never reported back (crash, manual test stopped...) is closed as failed
    for stale in db.scalars(select(SyncRun).where(SyncRun.status == "running", SyncRun.source == data.source)).all():
        stale.status, stale.finished_at, stale.error = "failed", utcnow(), "Interrompu (jamais clôturé)"
    run = SyncRun(source=data.source, cursor_before=after)
    db.add(run)
    db.commit()
    query = f"{BASE_QUERY} after:{after}" if after else INITIAL_QUERY
    return SyncStartOut(run_id=run.id, after_epoch=after, gmail_query=query)


@router.post("/sync-runs/{run_id}/finish", summary="Clôturer une synchronisation (avance le curseur si succès)")
def finish_sync(run_id: int, data: SyncFinishIn, db: Session = Depends(get_db)):
    run = db.get(SyncRun, run_id)
    if run is None:
        raise HTTPException(404, "Synchronisation introuvable")
    if run.status != "running":
        return {"run_id": run.id, "status": run.status}
    run.status = data.status
    run.finished_at = utcnow()
    run.fetched_count = data.fetched_count
    run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    run.error = data.error[:500] if data.error else None
    if data.status == "success":
        # Next run fetches what arrived after this run *started*
        run.cursor_after = int(run.started_at.replace(tzinfo=timezone.utc).timestamp())
    db.commit()
    events.publish("sync", {"run_id": run.id, "status": run.status, "inserted": run.inserted_count})
    log.info("sync run %s %s: fetched=%s inserted=%s dup=%s in %sms", run.id, run.status,
             run.fetched_count, run.inserted_count, run.duplicate_count, run.duration_ms)
    return {"run_id": run.id, "status": run.status, "duration_ms": run.duration_ms}


@router.post("/emails", response_model=IngestOut, summary="Recevoir un lot d'e-mails (idempotent)")
def ingest(data: IngestIn, db: Session = Depends(get_db)):
    run = db.get(SyncRun, data.run_id) if data.run_id else None
    new_ids, duplicates = ingest_emails(db, data.emails, run.id if run else None)
    if run:
        run.inserted_count += len(new_ids)
        run.duplicate_count += duplicates
        db.commit()
    if new_ids:
        events.publish("emails", {"new": len(new_ids)})
    return IngestOut(inserted=len(new_ids), duplicates=duplicates, new_ids=list(new_ids.values()), ids_by_message=new_ids)


@router.post("/emails/unknown", response_model=KnownIdsOut,
             summary="Parmi ces identifiants Gmail, lesquels ne sont pas encore importés (évite de relire Gmail)")
def unknown_ids(data: KnownIdsIn, db: Session = Depends(get_db)):
    ids = list(dict.fromkeys(data.gmail_ids))
    known: set[str] = set()
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        known.update(db.scalars(select(Email.gmail_message_id).where(Email.gmail_message_id.in_(chunk))).all())
    return KnownIdsOut(total=len(ids), unknown=[i for i in ids if i not in known])


@router.get("/classification/pending", response_model=list[PendingClassification],
            summary="E-mails à classer (contenu masqué : téléphones, IBAN)")
def pending_classification(limit: int = Query(default=10, ge=1, le=50), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Email)
        .where(Email.classification_status == "pending", Email.classification_attempts < MAX_ATTEMPTS)
        .order_by(Email.received_at.desc())
        .limit(limit)
    ).all()
    return [
        PendingClassification(
            id=e.id,
            from_email=e.from_email,
            subject=mask_sensitive(e.subject),
            text=mask_sensitive(e.body_text)[:3000],
            attempts=e.classification_attempts,
        )
        for e in rows
    ]


@router.post("/classification", response_model=ClassificationOut,
             summary="Sortie brute de l'IA : validée, sinon nouvelle tentative puis repli « autre / à vérifier »")
def classification(data: ClassificationIn, db: Session = Depends(get_db)):
    email = db.get(Email, data.email_id)
    if email is None:
        raise HTTPException(404, "E-mail introuvable")
    if email.classification_status != "pending":
        return ClassificationOut(result="ok", email_id=email.id, category=email.category, priority=email.priority)
    result, error = apply_classification(db, email, data.raw_output, data.attempt)
    if result != "retry":
        events.publish("email", {"email_id": email.id})
    return ClassificationOut(result=result, email_id=email.id, category=email.category,
                             priority=email.priority, error=error)


@router.post("/replies/{reply_id}/status", summary="Statut d'envoi renvoyé par le workflow d'envoi")
def reply_status(reply_id: int, data: ReplyStatusIn, db: Session = Depends(get_db)):
    reply = db.get(SentReply, reply_id)
    if reply is None:
        raise HTTPException(404, "Réponse introuvable")
    replies.record_status(db, reply, data.status, data.gmail_message_id, data.error)
    return {"reply_id": reply.id, "status": reply.status}


@router.post("/errors", status_code=201, summary="Enregistrer l'échec d'un workflow (Error Trigger)")
def workflow_error(data: WorkflowErrorIn, db: Session = Depends(get_db)):
    err = WorkflowError(**data.model_dump())
    db.add(err)
    # A sync that crashed must not stay "running" forever nor move the cursor
    for run in db.scalars(select(SyncRun).where(SyncRun.status == "running")).all():
        if "sync" in data.workflow.lower():
            run.status, run.finished_at, run.error = "failed", utcnow(), data.message[:500]
    db.commit()
    events.publish("error", {"workflow": data.workflow})
    log.warning("workflow error in %s (node %s)", data.workflow, data.node)
    return {"id": err.id}
