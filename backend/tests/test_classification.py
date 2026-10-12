import json

import pytest

from app.models import Email
from app.services.classification import parse_ai_output
from app.services.masking import mask_sensitive

from .conftest import WEBHOOK_SECRET, make_email, post_webhook

VALID = json.dumps({"category": "client", "priority": 1, "summary": "Un client demande un devis.", "action": "Envoyer le devis"})


@pytest.fixture
def email_id(client):
    return post_webhook(client, "/emails", {"emails": [make_email("msg-1")]}).json()["new_ids"][0]


def classify(client, email_id, raw, attempt):
    return post_webhook(client, "/classification", {"email_id": email_id, "raw_output": raw, "attempt": attempt}).json()


# ---------- parser ----------

@pytest.mark.parametrize("raw", [VALID, f"```json\n{VALID}\n```", VALID.replace('"client"', '" Client "')])
def test_parser_accepts_valid_outputs(raw):
    assert parse_ai_output(raw).value is not None


@pytest.mark.parametrize(
    "raw",
    [
        "Voici la classification : client, priorité 1",                    # not JSON
        '{"category": "client", "priority": 1, "summary": "x"}',           # missing field
        VALID.replace('"client"', '"urgent"'),                              # outside the closed list
        VALID.replace('"priority": 1', '"priority": 5'),                    # out of range
        VALID.replace('"priority": 1', '"priority": "1"'),                  # wrong type
        "[1, 2, 3]",                                                        # not an object
        "",
    ],
)
def test_parser_rejects_invalid_outputs(raw):
    result = parse_ai_output(raw)
    assert result.value is None and result.error


# ---------- full policy through the webhook ----------

def test_valid_output_is_stored(client, db, email_id):
    res = classify(client, email_id, VALID, attempt=1)
    assert res["result"] == "ok"
    e = db.get(Email, email_id)
    assert (e.category, e.priority, e.classification_status, e.needs_review) == ("client", 1, "done", False)
    assert e.classification_first_try_valid is True


def test_invalid_output_asks_for_one_retry_then_succeeds(client, db, email_id):
    assert classify(client, email_id, "pas du json", attempt=1)["result"] == "retry"
    assert db.get(Email, email_id).classification_status == "pending"
    assert classify(client, email_id, VALID, attempt=2)["result"] == "ok"
    db.expire_all()
    assert db.get(Email, email_id).classification_first_try_valid is False


def test_invalid_twice_falls_back_to_autre_and_review(client, db, email_id):
    classify(client, email_id, "pas du json", attempt=1)
    res = classify(client, email_id, '{"category": "???"}', attempt=2)
    assert res["result"] == "fallback" and res["category"] == "autre"
    db.expire_all()
    e = db.get(Email, email_id)
    assert e.needs_review is True and e.classification_status == "review"


def test_pending_list_masks_phone_numbers_and_ibans(client, email_id):
    r = client.get("/api/webhooks/n8n/classification/pending", headers={"X-Webhook-Secret": WEBHOOK_SECRET})
    assert r.status_code == 200
    text = r.json()[0]["text"]
    assert "06 12 34 56 78" not in text and "[téléphone masqué]" in text


@pytest.mark.parametrize(
    "raw,hidden",
    [
        ("Appelez le +33 6 12 34 56 78", "+33 6 12 34 56 78"),
        ("tel 0612345678 merci", "0612345678"),
        ("IBAN : FR76 3000 6000 0112 3456 7890 189", "FR76 3000 6000 0112 3456 7890 189"),
    ],
)
def test_masking(raw, hidden):
    assert hidden not in mask_sensitive(raw)


def test_masking_keeps_dates_and_amounts():
    text = "Facture FA-2025-0012 du 12/03/2025, montant 1 250,00 €"
    assert mask_sensitive(text) == text
