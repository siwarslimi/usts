from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["client", "facture", "rendez-vous", "newsletter", "spam probable", "autre"]
Status = Literal["to_process", "draft_ready", "replied", "ignored"]
Tone = Literal["formel", "neutre", "court"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------

class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=255)


class UserOut(ORM):
    id: int
    email: str


# ---------- emails ----------

class EmailListItem(ORM):
    id: int
    thread_id: int
    from_name: str
    from_email: str
    subject: str
    snippet: str
    received_at: datetime
    category: str | None
    priority: int | None
    ai_summary: str | None
    needs_review: bool
    classification_status: str
    status: str
    thread_size: int = 1


class EmailPage(BaseModel):
    items: list[EmailListItem]
    total: int
    page: int
    page_size: int
    pages: int


class EmailDetail(EmailListItem):
    to: list[str]
    cc: list[str]
    body_text: str
    expected_action: str | None


class EmailPatch(BaseModel):
    status: Status


class DraftIn(BaseModel):
    tone: Tone = "neutre"


class DraftOut(ORM):
    id: int
    email_id: int
    tone: str
    body: str
    source: str
    created_at: datetime


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    draft_id: int | None = None


class ReplyOut(ORM):
    id: int
    email_id: int
    status: str
    body: str
    error: str | None
    attempts: int
    created_at: datetime
    sent_at: datetime | None


class ThreadMessage(BaseModel):
    kind: Literal["incoming", "outgoing"]
    id: int
    from_name: str
    from_email: str
    to: list[str]
    body_text: str
    at: datetime
    status: str | None = None  # outgoing only
    error: str | None = None


class ThreadOut(BaseModel):
    id: int
    subject: str
    messages: list[ThreadMessage]
    emails: list[EmailDetail]
    latest_draft: DraftOut | None
    replies: list[ReplyOut]


# ---------- summary ----------

class PriorityItem(BaseModel):
    email: EmailListItem
    score: int
    reasons: list[str]


class SummaryOut(BaseModel):
    date: str
    received: int
    by_category: dict[str, int]
    by_status: dict[str, int]
    to_review: int
    text: str
    text_source: Literal["ai", "template"]
    top: list[PriorityItem]


# ---------- n8n webhooks ----------

class IncomingEmail(BaseModel):
    gmail_message_id: str = Field(min_length=1, max_length=64)
    gmail_thread_id: str = Field(min_length=1, max_length=64)
    from_name: str = ""
    from_email: str = Field(min_length=3, max_length=255)
    to: list[str] = []
    cc: list[str] = []
    subject: str = ""
    body_text: str = ""
    received_at: datetime
    rfc_message_id: str | None = None
    references: str | None = None


class IngestIn(BaseModel):
    run_id: int | None = None
    emails: list[IncomingEmail] = Field(max_length=500)


class IngestOut(BaseModel):
    inserted: int
    duplicates: int
    new_ids: list[int]
    ids_by_message: dict[str, int] = {}


class KnownIdsIn(BaseModel):
    gmail_ids: list[str] = Field(max_length=10000)


class KnownIdsOut(BaseModel):
    total: int
    unknown: list[str]


class SyncStartIn(BaseModel):
    source: Literal["gmail", "demo"] = "gmail"


class SyncStartOut(BaseModel):
    run_id: int
    after_epoch: int | None
    gmail_query: str


class SyncFinishIn(BaseModel):
    status: Literal["success", "failed"]
    fetched_count: int = 0
    error: str | None = None


class PendingClassification(BaseModel):
    id: int
    from_email: str
    subject: str
    text: str
    attempts: int


class ClassificationIn(BaseModel):
    email_id: int
    raw_output: str = Field(max_length=20000)
    attempt: int = Field(ge=1, le=5)


class ClassificationOut(BaseModel):
    result: Literal["ok", "retry", "fallback"]
    email_id: int
    category: str | None = None
    priority: int | None = None
    error: str | None = None


class ReplyStatusIn(BaseModel):
    status: Literal["sent", "failed"]
    gmail_message_id: str | None = None
    error: str | None = Field(default=None, max_length=500)


class WorkflowErrorIn(BaseModel):
    workflow: str = Field(max_length=255)
    node: str | None = Field(default=None, max_length=255)
    message: str = Field(max_length=1000)
    execution_id: str | None = Field(default=None, max_length=64)
