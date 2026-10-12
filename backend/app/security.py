import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

COOKIE_NAME = "mail_session"
SECRET_HEADER = "X-Webhook-Secret"
SIGNATURE_HEADER = "X-Signature"


# ---------- passwords ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


# ---------- session (JWT in an httpOnly cookie) ----------

def create_session_token(user: User) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "iat": now, "exp": now + timedelta(hours=s.jwt_ttl_hours)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Non authentifié")
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalide ou expirée")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalide")
    return user


# ---------- webhooks between n8n and the backend ----------

def sign_body(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def verify_webhook(request: Request) -> None:
    """Shared secret in a header (mandatory) + optional/mandatory HMAC of the raw body."""
    s = get_settings()
    provided = request.headers.get(SECRET_HEADER, "")
    if not provided or not hmac.compare_digest(provided.encode(), s.webhook_secret.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Secret de webhook manquant ou invalide")

    signature = request.headers.get(SIGNATURE_HEADER)
    # A GET has no body to protect: the shared secret is enough
    if signature is None and (not s.webhook_hmac_required or request.method == "GET"):
        return
    if signature is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Signature HMAC manquante")
    expected = sign_body(await request.body(), s.webhook_secret)
    if not hmac.compare_digest(signature.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Signature HMAC invalide")
