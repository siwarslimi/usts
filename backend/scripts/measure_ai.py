"""Measure the share of AI outputs that are valid on the first try, on the demo set.

Sends each demo email to Groq with *exactly* the request built by the n8n
classification workflow (system prompt read from the exported workflow) and
validates the answer with the backend parser. Nothing is written to the database.

    GROQ_API_KEY=... python scripts/measure_ai.py --workflow ../n8n/workflows/2-classification-ia.json
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# The app's settings require these, but this script never uses them (no database, no webhooks)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "unused-by-measure-script")
os.environ.setdefault("WEBHOOK_SECRET", "unused-by-measure-script")
from app.services.classification import parse_ai_output  # noqa: E402
from app.services.masking import mask_sensitive  # noqa: E402

DATA = Path(__file__).with_name("demo_emails.json")


def system_prompt(workflow: Path) -> str:
    wf = json.loads(workflow.read_text(encoding="utf-8"))
    node = next(n for n in wf["nodes"] if n["name"] == "Groq : classer (essai 1)")
    m = re.search(r"role: 'system', content: (\".*?\") \}", node["parameters"]["body"])
    return json.loads(m.group(1))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workflow", type=Path, required=True)
    p.add_argument("--model", default=os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b"))
    p.add_argument("--pause", type=float, default=2.0, help="seconds between calls (same as the workflow)")
    args = p.parse_args()
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        sys.exit("GROQ_API_KEY manquant")

    system = system_prompt(args.workflow)
    emails = json.loads(DATA.read_text(encoding="utf-8"))
    valid, agree, latencies, rows = 0, 0, [], []
    for e in emails:
        user = f"Expéditeur : {e['from'][1]}\nObjet : {mask_sensitive(e['subject'])}\n\n{mask_sensitive(e['body'])[:3000]}"
        body = {"model": args.model, "temperature": 0.2, "response_format": {"type": "json_object"}, "max_tokens": 300,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        for attempt in range(5):  # only HTTP 429 is retried; it is not an invalid output
            t0 = time.perf_counter()
            r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body,
                           headers={"Authorization": f"Bearer {key}"}, timeout=60)
            if r.status_code != 429:
                break
            time.sleep(float(r.headers.get("retry-after", 10)))
        latencies.append(time.perf_counter() - t0)
        raw = r.json()["choices"][0]["message"]["content"] if r.status_code == 200 else ""
        parsed = parse_ai_output(raw).value
        valid += parsed is not None
        agree += bool(parsed and parsed.category == e["label"]["category"])
        rows.append((e["id"], e["label"]["category"], parsed.category if parsed else f"INVALIDE ({r.status_code})"))
        time.sleep(args.pause)

    n = len(emails)
    for row in rows:
        print("  {:9} attendu={:14} obtenu={}".format(*row))
    print(f"\nModèle : {args.model}")
    print(f"Sorties valides du premier coup : {valid}/{n} ({valid / n:.0%})")
    print(f"Catégorie identique à l'étiquette du jeu de démo : {agree}/{n} ({agree / n:.0%})")
    print(f"Latence médiane : {sorted(latencies)[n // 2]:.2f} s")


if __name__ == "__main__":
    main()
