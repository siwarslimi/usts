"""The "Aujourd'hui" block: daily figures, a global summary and the 5 emails to handle first.

The ranking is deterministic and explainable: each point added to the score
comes with a human-readable reason shown in the UI.
"""
from collections import Counter
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import CATEGORIES, STATUSES, Email, utcnow
from . import ai

CATEGORY_WEIGHT = {"client": 6, "facture": 5, "rendez-vous": 5, "autre": 2, "newsletter": -20, "spam probable": -30}
CATEGORY_REASON = {
    "client": "Demande d'un client",
    "facture": "Facture / paiement",
    "rendez-vous": "Rendez-vous à confirmer",
}
PRIORITY_REASON = {1: "Priorité haute", 2: "Priorité moyenne"}

_summary_cache: dict[tuple, str] = {}


def day_bounds_utc(d: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(get_settings().app_timezone)
    start = datetime.combine(d, time.min, tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end = datetime.combine(d + timedelta(days=1), time.min, tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return start, end


def today_local() -> date:
    return datetime.now(ZoneInfo(get_settings().app_timezone)).date()


def score_email(e: Email, now: datetime, day_start: datetime) -> tuple[int, list[str]]:
    score, reasons = 0, []
    if e.priority:
        score += (4 - e.priority) * 10
        if e.priority in PRIORITY_REASON:
            reasons.append(PRIORITY_REASON[e.priority])
    if e.category:
        score += CATEGORY_WEIGHT.get(e.category, 0)
        if e.category in CATEGORY_REASON:
            reasons.append(CATEGORY_REASON[e.category])
    waited_days = (now - e.received_at).days
    if waited_days >= 1:
        score += min(waited_days, 5) * 2
        reasons.append(f"En attente depuis {waited_days} jour{'s' if waited_days > 1 else ''}")
    elif e.received_at >= day_start:
        score += 1
        reasons.append("Reçu aujourd'hui")
    if e.needs_review:
        score += 3
        reasons.append("Classement IA à vérifier")
    if e.status == "draft_ready":
        score -= 2
        reasons.append("Brouillon déjà prêt")
    if e.expected_action:
        reasons.append(f"Action : {e.expected_action}")
    return score, reasons


def build_summary(db: Session, d: date) -> dict:
    start, end = day_bounds_utc(d)
    day_emails = db.scalars(select(Email).where(Email.received_at >= start, Email.received_at < end)).all()

    by_category = Counter(e.category or "non classé" for e in day_emails)
    by_status = Counter(e.status for e in day_emails)
    to_review = sum(1 for e in day_emails if e.needs_review)

    # Candidates: anything still waiting for an answer up to the end of the selected day
    candidates = db.scalars(
        select(Email).where(Email.status.in_(("to_process", "draft_ready")), Email.received_at < end)
    ).all()
    now = min(utcnow(), end)
    ranked = sorted(
        ((e, *score_email(e, now, start)) for e in candidates if e.category not in ("newsletter", "spam probable")),
        key=lambda t: (-t[1], t[0].received_at),
    )[:5]

    lines = [f"- [{e.category or '?'}] {e.from_name or e.from_email} : {e.ai_summary or e.subject}" for e in day_emails]
    key = (d.isoformat(), len(day_emails), tuple(sorted(by_category.items())))
    text = _summary_cache.get(key)
    source = "ai" if text else "template"
    if text is None:
        text = ai.generate_day_summary(lines)
        if text:
            _summary_cache[key] = text
            source = "ai"
    if text is None:
        text = template_summary(len(day_emails), by_category, by_status, to_review, ranked)
        source = "template"

    thread_sizes = dict(
        db.execute(select(Email.thread_id, func.count()).where(Email.thread_id.in_([t[0].thread_id for t in ranked])).group_by(Email.thread_id)).all()
    )
    return {
        "date": d.isoformat(),
        "received": len(day_emails),
        "by_category": {c: by_category.get(c, 0) for c in (*CATEGORIES, "non classé") if by_category.get(c)},
        "by_status": {s: by_status.get(s, 0) for s in STATUSES},
        "to_review": to_review,
        "text": text,
        "text_source": source,
        "top": [
            {"email": {**_as_item(e), "thread_size": thread_sizes.get(e.thread_id, 1)}, "score": score, "reasons": reasons}
            for e, score, reasons in ranked
        ],
    }


def _as_item(e: Email) -> dict:
    from ..schemas import EmailListItem

    return EmailListItem.model_validate(e).model_dump()


def template_summary(total, by_category, by_status, to_review, ranked) -> str:
    if total == 0:
        return "Aucun e-mail reçu sur cette journée."
    labels = {"client": ("client", "clients"), "facture": ("facture", "factures"),
              "rendez-vous": ("rendez-vous", "rendez-vous"), "newsletter": ("newsletter", "newsletters"),
              "spam probable": ("spam probable", "spams probables"), "autre": ("autre", "autres"),
              "non classé": ("non classé", "non classés")}
    parts = [f"{n} {labels[c][n > 1]}" for c, n in by_category.most_common() if n]
    text = f"{total} e-mail{'s' if total > 1 else ''} reçu{'s' if total > 1 else ''} ce jour ({', '.join(parts)}). "
    pending = by_status.get("to_process", 0) + by_status.get("draft_ready", 0)
    text += f"{pending} en attente de réponse, {by_status.get('replied', 0)} déjà traité{'s' if by_status.get('replied', 0) > 1 else ''}."
    if to_review:
        text += f" {to_review} classement{'s' if to_review > 1 else ''} IA à vérifier."
    if ranked:
        top = ranked[0][0]
        text += f" Priorité n°1 : {top.ai_summary or top.subject}"
        if not text.endswith("."):
            text += "."
    return text
