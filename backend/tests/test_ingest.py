from sqlalchemy import func, select

from app.models import Email, SyncRun, Thread

from .conftest import make_email, post_webhook


def test_same_email_imported_twice_is_stored_once(client, db):
    r1 = post_webhook(client, "/emails", {"emails": [make_email("msg-1")]})
    r2 = post_webhook(client, "/emails", {"emails": [make_email("msg-1")]})

    assert r1.status_code == 200 and r1.json()["inserted"] == 1
    assert r2.status_code == 200 and r2.json()["inserted"] == 0 and r2.json()["duplicates"] == 1
    assert db.scalar(select(func.count()).select_from(Email)) == 1


def test_duplicate_inside_the_same_batch(client, db):
    r = post_webhook(client, "/emails", {"emails": [make_email("msg-1"), make_email("msg-1"), make_email("msg-2")]})
    assert r.json()["inserted"] == 2
    assert r.json()["duplicates"] == 1
    assert db.scalar(select(func.count()).select_from(Email)) == 2


def test_messages_of_same_gmail_thread_share_a_thread(client, db, auth_client):
    post_webhook(client, "/emails", {"emails": [make_email("m1", "t1"), make_email("m2", "t1", from_email="alice@client.fr")]})
    assert db.scalar(select(func.count()).select_from(Thread)) == 1
    thread_id = db.scalar(select(Thread.id))
    thread = auth_client.get(f"/api/threads/{thread_id}").json()
    assert [m["id"] for m in thread["messages"]] == sorted(m["id"] for m in thread["messages"])
    assert len(thread["messages"]) == 2


def test_sync_cursor_advances_only_on_success(client, db):
    first = post_webhook(client, "/sync-runs", {"source": "gmail"}).json()
    assert first["after_epoch"] is None and "newer_than" in first["gmail_query"]

    post_webhook(client, "/emails", {"run_id": first["run_id"], "emails": [make_email("a"), make_email("b")]})
    post_webhook(client, f"/sync-runs/{first['run_id']}/finish", {"status": "success", "fetched_count": 2})

    run = db.get(SyncRun, first["run_id"])
    assert run.inserted_count == 2 and run.cursor_after is not None

    second = post_webhook(client, "/sync-runs", {"source": "gmail"}).json()
    assert second["after_epoch"] == run.cursor_after - 300
    post_webhook(client, f"/sync-runs/{second['run_id']}/finish", {"status": "failed", "error": "boom"})

    third = post_webhook(client, "/sync-runs", {"source": "gmail"}).json()
    assert third["after_epoch"] == second["after_epoch"], "a failed run must not move the cursor"


def test_messy_gmail_data_is_cleaned(client, db):
    long_subject = "x" * 2000
    r = post_webhook(client, "/emails", {"emails": [make_email("nul-1", body_text="a\x00b", subject=long_subject)]})
    assert r.json()["inserted"] == 1
    e = db.scalar(select(Email))
    assert e.body_text == "ab" and len(e.subject) == 998


def test_unknown_ids_lets_n8n_skip_already_imported_messages(client):
    post_webhook(client, "/emails", {"emails": [make_email("known-1")]})
    r = post_webhook(client, "/emails/unknown", {"gmail_ids": ["known-1", "new-1", "new-2", "new-1"]})
    assert r.status_code == 200
    assert r.json() == {"total": 3, "unknown": ["new-1", "new-2"]}


def test_unfinished_run_is_closed_when_a_new_one_starts(client, db):
    first = post_webhook(client, "/sync-runs", {"source": "gmail"}).json()["run_id"]
    post_webhook(client, "/sync-runs", {"source": "gmail"})
    db.expire_all()
    assert db.get(SyncRun, first).status == "failed"
