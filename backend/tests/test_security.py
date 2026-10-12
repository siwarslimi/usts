import json

import pytest

from app.config import get_settings
from app.security import SECRET_HEADER, SIGNATURE_HEADER, sign_body

from .conftest import WEBHOOK_SECRET, make_email, post_webhook


def test_webhook_without_secret_is_rejected(client):
    r = post_webhook(client, "/emails", {"emails": [make_email()]}, secret=None)
    assert r.status_code == 401


def test_webhook_with_wrong_secret_is_rejected(client):
    r = post_webhook(client, "/emails", {"emails": [make_email()]}, secret="not-the-right-secret-at-all")
    assert r.status_code == 401


def test_webhook_with_valid_secret_is_accepted(client):
    assert post_webhook(client, "/emails", {"emails": [make_email()]}).status_code == 200


def test_webhook_with_tampered_body_is_rejected(client):
    body = json.dumps({"emails": [make_email()]}).encode()
    headers = {
        "Content-Type": "application/json",
        SECRET_HEADER: WEBHOOK_SECRET,
        SIGNATURE_HEADER: sign_body(body.replace(b"Alice", b"Mallory"), WEBHOOK_SECRET),
    }
    assert client.post("/api/webhooks/n8n/emails", content=body, headers=headers).status_code == 401


def test_hmac_required_mode_rejects_unsigned_calls(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "webhook_hmac_required", True)
    assert post_webhook(client, "/emails", {"emails": [make_email()]}, sign=False).status_code == 401
    assert post_webhook(client, "/emails", {"emails": [make_email()]}, sign=True).status_code == 200


@pytest.mark.parametrize("path", ["/api/emails", "/api/summary", "/api/threads/1", "/api/stats", "/api/events"])
def test_no_data_without_authentication(client, path):
    assert client.get(path).status_code == 401


def test_login_rejects_bad_password_and_password_is_hashed(client, db):
    from sqlalchemy import select

    from app.models import User

    assert client.post("/api/auth/login", json={"email": "admin@test.local", "password": "nope"}).status_code == 401
    user = db.scalar(select(User))
    assert user.password_hash.startswith("$2") and "correct horse" not in user.password_hash


def test_session_cookie_is_httponly(client):
    r = client.post("/api/auth/login", json={"email": "admin@test.local", "password": "correct horse battery staple"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_get_webhook_needs_secret_but_no_signature(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "webhook_hmac_required", True)
    url = "/api/webhooks/n8n/classification/pending"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={SECRET_HEADER: WEBHOOK_SECRET}).status_code == 200
