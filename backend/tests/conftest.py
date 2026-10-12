import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL=f"sqlite:///{_tmp}/test.db",
    JWT_SECRET="test-jwt-secret-0123456789",
    WEBHOOK_SECRET="test-webhook-secret-0123456789",
    ADMIN_EMAIL="admin@test.local",
    ADMIN_PASSWORD="correct horse battery staple",
    REPLY_TRANSPORT="mock",
    GROQ_API_KEY="",
    WEBHOOK_HMAC_REQUIRED="false",
)

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app, init_db  # noqa: E402
from app.security import SECRET_HEADER, SIGNATURE_HEADER, sign_body  # noqa: E402

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    init_db()
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    r = client.post("/api/auth/login", json={"email": "admin@test.local", "password": "correct horse battery staple"})
    assert r.status_code == 200
    return client


def post_webhook(client, path: str, payload: dict, secret: str | None = WEBHOOK_SECRET, sign: bool = True):
    body = json.dumps(payload, default=str).encode()
    headers = {"Content-Type": "application/json"}
    if secret is not None:
        headers[SECRET_HEADER] = secret
        if sign:
            headers[SIGNATURE_HEADER] = sign_body(body, secret)
    return client.post(f"/api/webhooks/n8n{path}", content=body, headers=headers)


def make_email(msg_id: str = "msg-1", thread_id: str = "thr-1", **kw) -> dict:
    data = {
        "gmail_message_id": msg_id,
        "gmail_thread_id": thread_id,
        "from_name": "Alice Martin",
        "from_email": "alice@client.fr",
        "to": ["moi@test.local"],
        "subject": "Demande de devis",
        "body_text": "Bonjour, pouvez-vous m'envoyer un devis ? Mon numéro : 06 12 34 56 78.",
        "received_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "rfc_message_id": f"<{msg_id}@mail.test>",
    }
    data.update(kw)
    return data
