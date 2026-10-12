"""Validation of the AI classification output and the retry / fallback policy.

Policy (from the spec):
  * valid JSON matching the schema            -> stored, status "done"
  * invalid on the 1st attempt                -> caller (n8n) must retry once
  * invalid on the 2nd attempt (or later)     -> category "autre", flagged "à vérifier"
"""
import json
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from ..models import CATEGORIES, Email

MAX_ATTEMPTS = 2
FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


class AIClassification(BaseModel):
    category: Literal["client", "facture", "rendez-vous", "newsletter", "spam probable", "autre"]
    priority: int = Field(ge=1, le=3, strict=True)
    summary: str = Field(min_length=1, max_length=400)
    action: str = Field(min_length=1, max_length=300)

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("summary", "action", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


@dataclass
class ParseResult:
    value: AIClassification | None
    error: str | None


def parse_ai_output(raw: str) -> ParseResult:
    """Accepts a bare JSON object, optionally wrapped in a markdown code fence. Nothing else."""
    text = raw.strip()
    m = FENCE_RE.match(text)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return ParseResult(None, f"JSON invalide : {e.msg}")
    if not isinstance(data, dict):
        return ParseResult(None, "La sortie n'est pas un objet JSON")
    try:
        return ParseResult(AIClassification.model_validate(data), None)
    except ValidationError as e:
        first = e.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        return ParseResult(None, f"Schéma invalide ({loc}) : {first['msg']}")


def apply_classification(db: Session, email: Email, raw: str, attempt: int) -> tuple[str, str | None]:
    """Returns ("ok" | "retry" | "fallback", error)."""
    result = parse_ai_output(raw)
    email.classification_attempts = max(email.classification_attempts, attempt)

    if result.value is not None:
        v = result.value
        email.category = v.category
        email.priority = v.priority
        email.ai_summary = v.summary
        email.expected_action = v.action
        email.needs_review = False
        email.classification_status = "done"
        email.classification_first_try_valid = attempt == 1
        db.commit()
        return "ok", None

    if attempt < MAX_ATTEMPTS:
        db.commit()
        return "retry", result.error

    email.category = "autre"
    email.priority = email.priority or 2
    email.ai_summary = None
    email.expected_action = "Classer manuellement"
    email.needs_review = True
    email.classification_status = "review"
    email.classification_first_try_valid = False
    db.commit()
    return "fallback", result.error


assert set(AIClassification.model_fields["category"].annotation.__args__) == set(CATEGORIES)
