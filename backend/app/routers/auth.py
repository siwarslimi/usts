import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User
from ..schemas import LoginIn, UserOut
from ..security import COOKIE_NAME, create_session_token, current_user, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Light brute-force protection: 10 failed attempts per IP per 5 minutes
_failures: dict[str, deque] = defaultdict(deque)
WINDOW, MAX_FAILURES = 300, 10


def _too_many(ip: str) -> bool:
    q = _failures[ip]
    while q and q[0] < time.monotonic() - WINDOW:
        q.popleft()
    return len(q) >= MAX_FAILURES


@router.post("/login", response_model=UserOut, summary="Connexion (pose un cookie de session httpOnly)")
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    if _too_many(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Trop de tentatives, réessayez dans quelques minutes")
    user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        _failures[ip].append(time.monotonic())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants incorrects")
    s = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(user),
        max_age=s.jwt_ttl_hours * 3600,
        httponly=True,
        secure=s.cookie_secure,
        samesite="strict",
        path="/",
    )
    return user


@router.post("/logout", status_code=204, summary="Déconnexion")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut, summary="Utilisateur connecté")
def me(user: User = Depends(current_user)):
    return user
