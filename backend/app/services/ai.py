"""AI helpers used directly by the backend: reply drafts and the daily summary.

Classification runs in n8n; drafts are generated here because the user waits for
them synchronously. Without GROQ_API_KEY, deterministic templates are used so the
demo keeps working end to end.
"""
import logging
import time

import httpx

from ..config import get_settings
from ..models import Email
from .masking import mask_sensitive

log = logging.getLogger("ai")

TONE_GUIDE = {
    "formel": "Ton formel et courtois, vouvoiement, formule de politesse complète.",
    "neutre": "Ton professionnel et chaleureux, vouvoiement, phrases simples.",
    "court": "Réponse très brève (2 à 3 phrases maximum), directe, vouvoiement.",
}


class AIUnavailable(Exception):
    pass


def ai_enabled() -> bool:
    return bool(get_settings().groq_api_key)


def chat(messages: list[dict], temperature: float = 0.4, max_tokens: int = 600) -> str:
    s = get_settings()
    if not s.groq_api_key:
        raise AIUnavailable("GROQ_API_KEY non configurée")
    payload = {"model": s.groq_model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    headers = {"Authorization": f"Bearer {s.groq_api_key}"}
    for attempt in range(3):
        try:
            r = httpx.post(f"{s.groq_base_url}/chat/completions", json=payload, headers=headers, timeout=30)
        except httpx.HTTPError as e:
            raise AIUnavailable(f"Fournisseur IA injoignable ({type(e).__name__})") from e
        if r.status_code == 429 and attempt < 2:
            wait = min(float(r.headers.get("retry-after", 2 * (attempt + 1))), 10)
            log.warning("AI quota reached (429), retrying in %.1fs", wait)
            time.sleep(wait)
            continue
        if r.status_code >= 400:
            raise AIUnavailable(f"Erreur du fournisseur IA (HTTP {r.status_code})")
        return r.json()["choices"][0]["message"]["content"].strip()
    raise AIUnavailable("Quota IA dépassé")


def _first_name(email: Email) -> str:
    name = (email.from_name or "").strip()
    return name.split()[0] if name else ""


def template_draft(email: Email, tone: str) -> str:
    first = _first_name(email)
    subject = email.subject or "votre message"
    if tone == "court":
        hello = f"Bonjour {first}," if first else "Bonjour,"
        return f"{hello}\n\nMerci pour votre message. C'est bien noté, je reviens vers vous rapidement.\n\nCordialement"
    if tone == "formel":
        hello = f"Madame, Monsieur{' ' + email.from_name if email.from_name else ''},"
        return (
            f"{hello}\n\nNous accusons bonne réception de votre message concernant « {subject} » "
            "et vous en remercions.\n\nNous étudions votre demande avec attention et ne manquerons pas "
            "de revenir vers vous dans les meilleurs délais.\n\nNous vous prions d'agréer, Madame, Monsieur, "
            "l'expression de nos salutations distinguées."
        )
    hello = f"Bonjour {first}," if first else "Bonjour,"
    return (
        f"{hello}\n\nMerci pour votre message au sujet de « {subject} ». "
        "Je le traite et je reviens vers vous très vite avec une réponse complète.\n\n"
        "Bonne journée,"
    )


def generate_draft(email: Email, thread_context: list[Email], tone: str) -> tuple[str, str]:
    """Returns (body, source) where source is "ai" or "template"."""
    if not ai_enabled():
        return template_draft(email, tone), "template"

    history = "\n\n".join(
        f"De : {m.from_name or m.from_email}\nDate : {m.received_at:%d/%m/%Y %H:%M}\n{mask_sensitive(m.body_text)[:1500]}"
        for m in thread_context[-4:]
    )
    messages = [
        {
            "role": "system",
            "content": (
                "Tu rédiges des brouillons de réponse à des e-mails professionnels, en français. "
                f"{TONE_GUIDE[tone]} N'invente aucun fait, prix, date ni engagement absent du fil : "
                "si une information manque, propose de la confirmer. Ne mets ni objet ni signature nominative. "
                "Réponds uniquement avec le corps du message."
            ),
        },
        {"role": "user", "content": f"Fil de discussion (le plus récent en dernier) :\n\n{history}\n\nRédige la réponse au dernier message."},
    ]
    try:
        return chat(messages), "ai"
    except AIUnavailable as e:
        log.warning("Draft generation fell back to template: %s", e)
        return template_draft(email, tone), "template"


def generate_day_summary(lines: list[str]) -> str | None:
    if not ai_enabled() or not lines:
        return None
    messages = [
        {
            "role": "system",
            "content": (
                "Tu es l'assistant d'une boîte mail professionnelle. À partir de la liste des e-mails du jour, "
                "écris en français un résumé global de 2 à 3 phrases : volume, sujets dominants, points urgents. "
                "Pas de liste, pas de titre."
            ),
        },
        {"role": "user", "content": "\n".join(lines[:40])},
    ]
    try:
        return chat(messages, temperature=0.3, max_tokens=220)
    except AIUnavailable as e:
        log.warning("Summary fell back to template: %s", e)
        return None
