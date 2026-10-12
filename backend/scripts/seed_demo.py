"""Inject ~30 fictional emails through the *real* n8n webhook endpoints (no Gmail needed).

It goes through the same path as the sync workflow: start a sync run, post batches
(signed with the shared secret + HMAC), finish the run. Running it twice proves
idempotency: the second run inserts 0 emails.

By default it also plays the role of the AI (--labels): it posts pre-written
classification outputs to the classification webhook, including invalid outputs
for two emails, to exercise the retry and "à vérifier" fallback paths.
Use --no-labels to leave the emails pending for the n8n classification workflow.

Only the Python standard library is used:
    python scripts/seed_demo.py --url http://localhost:8000 --secret "$WEBHOOK_SECRET"
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).with_name("demo_emails.json")
ME = "moi@assistant-demo.fr"


def call(url: str, secret: str, method: str, path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{url}/api/webhooks/n8n{path}", data=body, method=method)
    req.add_header("X-Webhook-Secret", secret)
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Signature", "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} on {path}: {e.read().decode(errors='replace')}")


def build_emails(now: datetime) -> list[dict]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    raw.sort(key=lambda m: -m["h"])  # oldest first, like a real inbox history
    previous_in_thread: dict[str, list[str]] = {}
    out = []
    for m in raw:
        rfc_id = f"<{m['id']}@demo.assistant>"
        refs = previous_in_thread.setdefault(m["thread"], [])
        out.append({
            "gmail_message_id": m["id"],
            "gmail_thread_id": m["thread"],
            "from_name": m["from"][0],
            "from_email": m["from"][1],
            "to": [ME],
            "cc": [],
            "subject": m["subject"],
            "body_text": m["body"],
            "received_at": (now - timedelta(hours=m["h"])).isoformat(),
            "rfc_message_id": rfc_id,
            "references": " ".join(refs) or None,
            "_label": m["label"],
            "_invalid": m.get("insist_invalid", 0),
        })
        refs.append(rfc_id)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=os.environ.get("BACKEND_URL", "http://localhost:8000"))
    p.add_argument("--secret", default=os.environ.get("WEBHOOK_SECRET"))
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument("--labels", action=argparse.BooleanOptionalAction, default=True,
                   help="simulate the AI classification (default) or leave emails pending for n8n")
    args = p.parse_args()
    if not args.secret:
        sys.exit("WEBHOOK_SECRET manquant (--secret ou variable d'environnement)")

    emails = build_emails(datetime.now(timezone.utc))
    t0 = time.perf_counter()
    run = call(args.url, args.secret, "POST", "/sync-runs", {"source": "demo"})
    inserted, duplicates, new_ids = 0, 0, {}
    for i in range(0, len(emails), args.batch_size):
        batch = emails[i:i + args.batch_size]
        payload = {"run_id": run["run_id"], "emails": [{k: v for k, v in e.items() if not k.startswith("_")} for e in batch]}
        res = call(args.url, args.secret, "POST", "/emails", payload)
        inserted += res["inserted"]
        duplicates += res["duplicates"]
        new_ids.update(res["ids_by_message"])
    call(args.url, args.secret, "POST", f"/sync-runs/{run['run_id']}/finish", {"status": "success", "fetched_count": len(emails)})
    elapsed = time.perf_counter() - t0
    print(f"Import : {inserted} insérés, {duplicates} doublons ignorés, {len(emails)} reçus en {elapsed * 1000:.0f} ms")

    if not args.labels or not new_ids:
        if not new_ids:
            print("Rien de nouveau à classer (jeu déjà importé).")
        return

    ok = retry = fallback = 0
    for e in emails:
        email_id = new_ids.get(e["gmail_message_id"])
        if email_id is None:
            continue
        valid = json.dumps(e["_label"], ensure_ascii=False)
        outputs = ["Voici ma classification : " + e["_label"]["category"]] * e["_invalid"] + [valid]
        for attempt, raw in enumerate(outputs[:2], start=1):
            res = call(args.url, args.secret, "POST", "/classification",
                       {"email_id": email_id, "raw_output": raw, "attempt": attempt})
            if res["result"] != "retry":
                break
            retry += 1
        ok += res["result"] == "ok"
        fallback += res["result"] == "fallback"
    print(f"Classification simulée : {ok} valides, {retry} nouvelles tentatives, {fallback} repli « à vérifier »")


if __name__ == "__main__":
    main()
