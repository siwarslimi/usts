import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .config import get_settings
from .db import Base, SessionLocal, engine
from .models import User
from .routers import auth, emails, system, webhooks
from .security import hash_password

# Access logs contain only method/path/status: no bodies, no cookies, no secrets.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


def init_db() -> None:
    Base.metadata.create_all(engine)
    s = get_settings()
    if not s.admin_password:
        return
    with SessionLocal() as db:
        email = s.admin_email.strip().lower()
        if db.scalar(select(User).where(User.email == email)) is None:
            db.add(User(email=email, password_hash=hash_password(s.admin_password)))
            db.commit()
            log.info("Admin account created")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=lifespan,
        title="Assistant de boîte mail — API",
        version="1.0.0",
        description=(
            "API entre l'interface web et n8n. Le site n'appelle jamais n8n : il passe par ces routes.\n\n"
            "* Routes utilisateur : cookie de session httpOnly (`POST /api/auth/login`).\n"
            "* Routes `/api/webhooks/n8n/*` : en-tête `X-Webhook-Secret` obligatoire, "
            "signature HMAC-SHA256 du corps dans `X-Signature` (`sha256=<hex>`)."
        ),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    origins = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                           allow_methods=["*"], allow_headers=["*"])
    for r in (auth.router, emails.router, webhooks.router, system.router):
        app.include_router(r, prefix="/api")

    return app


app = create_app()
