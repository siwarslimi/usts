import math
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Draft, Email, SentReply, Thread
from ..schemas import (
    Category,
    DraftIn,
    DraftOut,
    EmailDetail,
    EmailListItem,
    EmailPage,
    EmailPatch,
    ReplyIn,
    ReplyOut,
    Status,
    SummaryOut,
    ThreadMessage,
    ThreadOut,
)
from ..security import current_user
from ..services import ai, events, replies
from ..services.summary import build_summary, day_bounds_utc, today_local

router = APIRouter(tags=["emails"], dependencies=[Depends(current_user)])


def _get_email(db: Session, email_id: int) -> Email:
    email = db.get(Email, email_id)
    if email is None:
        raise HTTPException(404, "E-mail introuvable")
    return email


@router.get("/emails", response_model=EmailPage, summary="Liste paginée et filtrable des e-mails")
def list_emails(
    category: list[Category] = Query(default=[]),
    priority: list[int] = Query(default=[]),
    status: list[Status] = Query(default=[]),
    sender: str | None = Query(default=None, description="Adresse ou nom de l'expéditeur (contient)"),
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = Query(default=None, description="Recherche dans l'objet et le contenu"),
    needs_review: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(Email)
    if category:
        stmt = stmt.where(Email.category.in_(category))
    if priority:
        stmt = stmt.where(Email.priority.in_(priority))
    if status:
        stmt = stmt.where(Email.status.in_(status))
    if sender:
        like = f"%{sender.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Email.from_email).like(like), func.lower(Email.from_name).like(like)))
    if date_from:
        stmt = stmt.where(Email.received_at >= day_bounds_utc(date_from)[0])
    if date_to:
        stmt = stmt.where(Email.received_at < day_bounds_utc(date_to)[1])
    if q:
        for word in q.split()[:6]:
            like = f"%{word.lower()}%"
            stmt = stmt.where(or_(func.lower(Email.subject).like(like), func.lower(Email.body_text).like(like)))
    if needs_review is not None:
        stmt = stmt.where(Email.needs_review == needs_review)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Email.received_at.desc(), Email.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    sizes = dict(
        db.execute(
            select(Email.thread_id, func.count()).where(Email.thread_id.in_({e.thread_id for e in rows})).group_by(Email.thread_id)
        ).all()
    )
    items = [EmailListItem.model_validate(e).model_copy(update={"thread_size": sizes.get(e.thread_id, 1)}) for e in rows]
    return EmailPage(items=items, total=total, page=page, page_size=page_size, pages=max(1, math.ceil(total / page_size)))


@router.get("/emails/senders", response_model=list[dict], summary="Expéditeurs les plus fréquents (pour le filtre)")
def senders(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Email.from_email, func.max(Email.from_name), func.count())
        .group_by(Email.from_email)
        .order_by(func.count().desc())
        .limit(50)
    ).all()
    return [{"email": e, "name": n, "count": c} for e, n, c in rows]


@router.get("/emails/counts", summary="Compteurs par statut et par catégorie (barre latérale)")
def counts(db: Session = Depends(get_db)):
    by_status = dict(db.execute(select(Email.status, func.count()).group_by(Email.status)).all())
    by_category = dict(
        db.execute(
            select(Email.category, func.count()).where(Email.status.in_(("to_process", "draft_ready"))).group_by(Email.category)
        ).all()
    )
    review = db.scalar(select(func.count()).where(Email.needs_review.is_(True), Email.status != "ignored"))
    return {
        "total": sum(by_status.values()),
        "status": by_status,
        "category_open": {k or "non classé": v for k, v in by_category.items()},
        "to_review": review,
    }


@router.get("/emails/{email_id}", response_model=EmailDetail, summary="Détail d'un e-mail")
def get_email(email_id: int, db: Session = Depends(get_db)):
    return _get_email(db, email_id)


@router.patch("/emails/{email_id}", response_model=EmailDetail, summary="Changer le statut (ex. ignorer)")
def patch_email(email_id: int, data: EmailPatch, db: Session = Depends(get_db)):
    email = _get_email(db, email_id)
    email.status = data.status
    db.commit()
    events.publish("email", {"email_id": email.id})
    return email


@router.get("/threads/{thread_id}", response_model=ThreadOut, summary="Fil de discussion complet, dans l'ordre")
def get_thread(thread_id: int, db: Session = Depends(get_db)):
    thread = db.get(Thread, thread_id)
    if thread is None:
        raise HTTPException(404, "Fil introuvable")
    emails = thread.emails
    all_replies = [r for e in emails for r in e.replies]
    replies.expire_stuck(db, all_replies)

    messages = [
        ThreadMessage(kind="incoming", id=e.id, from_name=e.from_name, from_email=e.from_email, to=e.to,
                      body_text=e.body_text, at=e.received_at)
        for e in emails
    ] + [
        ThreadMessage(kind="outgoing", id=r.id, from_name="Moi", from_email="", to=[r.email.from_email],
                      body_text=r.body, at=r.sent_at or r.created_at, status=r.status, error=r.error)
        for r in all_replies
    ]
    messages.sort(key=lambda m: m.at)
    latest = emails[-1]
    latest_draft = db.scalar(select(Draft).where(Draft.email_id == latest.id).order_by(Draft.id.desc()).limit(1))
    return ThreadOut(
        id=thread.id,
        subject=thread.subject,
        messages=messages,
        emails=[EmailDetail.model_validate(e).model_copy(update={"thread_size": len(emails)}) for e in emails],
        latest_draft=latest_draft,
        replies=[ReplyOut.model_validate(r) for r in sorted(all_replies, key=lambda r: r.id)],
    )


@router.get("/summary", response_model=SummaryOut, summary="Bloc « Aujourd'hui » : résumé + 5 e-mails prioritaires")
def summary(date: date | None = None, db: Session = Depends(get_db)):
    return build_summary(db, date or today_local())


@router.post("/emails/{email_id}/draft", response_model=DraftOut, status_code=201, summary="Demander un brouillon IA")
def create_draft(email_id: int, data: DraftIn, db: Session = Depends(get_db)):
    email = _get_email(db, email_id)
    body, source = ai.generate_draft(email, email.thread.emails, data.tone)
    draft = Draft(email_id=email.id, tone=data.tone, body=body, source=source)
    db.add(draft)
    if email.status == "to_process":
        email.status = "draft_ready"
    db.commit()
    events.publish("email", {"email_id": email.id})
    return draft


@router.post(
    "/emails/{email_id}/reply",
    response_model=ReplyOut,
    status_code=202,
    summary="Envoyer une réponse (validée par l'utilisateur), idempotent via l'en-tête Idempotency-Key",
)
def reply(
    email_id: int,
    data: ReplyIn,
    background: BackgroundTasks,
    response: Response,
    idempotency_key: str = Header(min_length=8, max_length=64, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    email = _get_email(db, email_id)
    reply, created = replies.create_reply(db, email, data.body, data.draft_id, idempotency_key)
    if reply.email_id != email.id:
        raise HTTPException(409, "Clé d'idempotence déjà utilisée pour un autre e-mail")
    if created:
        background.add_task(replies.dispatch, reply.id)
    else:
        response.status_code = 200
    return reply


@router.post("/replies/{reply_id}/retry", response_model=ReplyOut, status_code=202, summary="Réessayer un envoi en échec")
def retry_reply(reply_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    reply = db.get(SentReply, reply_id)
    if reply is None:
        raise HTTPException(404, "Réponse introuvable")
    if not replies.claim_retry(db, reply_id):
        raise HTTPException(409, f"Impossible de réessayer : statut actuel « {reply.status} »")
    db.refresh(reply)
    events.publish("reply", {"reply_id": reply.id, "email_id": reply.email_id, "status": "sending"})
    background.add_task(replies.dispatch, reply.id)
    return reply
