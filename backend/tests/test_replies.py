import pytest
from sqlalchemy import func, select

from app.models import Email, SentReply
from app.services import replies

from .conftest import make_email, post_webhook


@pytest.fixture
def dispatched(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(replies, "dispatch", lambda reply_id: calls.append(reply_id))
    return calls


@pytest.fixture
def email_id(client):
    return post_webhook(client, "/emails", {"emails": [make_email("msg-1")]}).json()["new_ids"][0]


def test_same_reply_sent_twice_goes_out_once(auth_client, db, email_id, dispatched):
    headers = {"Idempotency-Key": "7f1c2a8e-double-click"}
    r1 = auth_client.post(f"/api/emails/{email_id}/reply", json={"body": "Merci !"}, headers=headers)
    r2 = auth_client.post(f"/api/emails/{email_id}/reply", json={"body": "Merci !"}, headers=headers)

    assert r1.status_code == 202
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    assert db.scalar(select(func.count()).select_from(SentReply)) == 1
    assert dispatched == [r1.json()["id"]], "the send workflow must be triggered exactly once"


def test_reply_requires_idempotency_key(auth_client, email_id, dispatched):
    r = auth_client.post(f"/api/emails/{email_id}/reply", json={"body": "Merci !"})
    assert r.status_code == 422
    assert dispatched == []


def test_retry_only_from_failed_and_only_once(auth_client, client, db, email_id, dispatched):
    reply_id = auth_client.post(f"/api/emails/{email_id}/reply", json={"body": "Merci"},
                                headers={"Idempotency-Key": "key-retry-0001"}).json()["id"]

    # Still "sending": a retry would risk a double send
    assert auth_client.post(f"/api/replies/{reply_id}/retry").status_code == 409

    post_webhook(client, f"/replies/{reply_id}/status", {"status": "failed", "error": "Gmail 500"})
    assert auth_client.post(f"/api/replies/{reply_id}/retry").status_code == 202
    assert auth_client.post(f"/api/replies/{reply_id}/retry").status_code == 409
    assert dispatched == [reply_id, reply_id]


def test_sent_callback_is_final_and_marks_email_replied(auth_client, client, db, email_id, dispatched):
    reply_id = auth_client.post(f"/api/emails/{email_id}/reply", json={"body": "Merci"},
                                headers={"Idempotency-Key": "key-final-0001"}).json()["id"]
    post_webhook(client, f"/replies/{reply_id}/status", {"status": "sent", "gmail_message_id": "g-1"})
    # A late, duplicated failure callback must not reopen a sent reply
    post_webhook(client, f"/replies/{reply_id}/status", {"status": "failed", "error": "late"})

    db.expire_all()
    assert db.get(SentReply, reply_id).status == "sent"
    assert db.get(Email, email_id).status == "replied"
    assert auth_client.post(f"/api/replies/{reply_id}/retry").status_code == 409


def test_mock_transport_sends_and_simulated_failure_can_be_retried(auth_client, db, email_id, monkeypatch):
    monkeypatch.setattr(replies.time, "sleep", lambda s: None)
    r = auth_client.post(f"/api/emails/{email_id}/reply", json={"body": "Test [test-echec]"},
                         headers={"Idempotency-Key": "key-mock-0001"})
    db.expire_all()
    assert db.get(SentReply, r.json()["id"]).status == "failed"
    auth_client.post(f"/api/replies/{r.json()['id']}/retry")
    db.expire_all()
    assert db.get(SentReply, r.json()["id"]).status == "sent"
