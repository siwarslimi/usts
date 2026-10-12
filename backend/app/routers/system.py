import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Email, SyncRun, WorkflowError
from ..security import current_user
from ..services import ai, events

router = APIRouter(tags=["system"])


@router.get("/health", summary="Sonde de vie")
def health():
    return {"ok": True}


@router.get("/events", summary="Flux temps réel (Server-Sent Events)", dependencies=[Depends(current_user)])
async def stream(request: Request):
    async def gen():
        last = events.current_seq()
        yield "retry: 3000\n\n"
        idle = 0
        while not await request.is_disconnected():
            batch = events.since(last)
            for seq, kind, data in batch:
                last = seq
                yield f"id: {seq}\nevent: {kind}\ndata: {json.dumps(data)}\n\n"
            idle = 0 if batch else idle + 1
            if idle >= 15:  # keep-alive comment every ~15 s
                idle = 0
                yield ": ping\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/stats", summary="Mesures : synchronisations, qualité des sorties IA, erreurs", dependencies=[Depends(current_user)])
def stats(db: Session = Depends(get_db)):
    runs = db.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(10)).all()
    classified = db.scalar(select(func.count()).where(Email.classification_first_try_valid.is_not(None)))
    first_try = db.scalar(select(func.count()).where(Email.classification_first_try_valid.is_(True)))
    pending = db.scalar(select(func.count()).where(Email.classification_status == "pending"))
    review = db.scalar(select(func.count()).where(Email.classification_status == "review"))
    errors = db.scalars(select(WorkflowError).order_by(WorkflowError.id.desc()).limit(10)).all()
    return {
        "ai_enabled": ai.ai_enabled(),
        "classification": {
            "classified": classified,
            "first_try_valid": first_try,
            "first_try_valid_rate": round(first_try / classified, 3) if classified else None,
            "pending": pending,
            "to_review": review,
        },
        "sync_runs": [
            {"id": r.id, "source": r.source, "status": r.status, "started_at": r.started_at, "duration_ms": r.duration_ms,
             "fetched": r.fetched_count, "inserted": r.inserted_count, "duplicates": r.duplicate_count, "error": r.error}
            for r in runs
        ],
        "workflow_errors": [
            {"id": e.id, "workflow": e.workflow, "node": e.node, "message": e.message, "at": e.created_at} for e in errors
        ],
    }
