"""Server-owned prototype sessions. One process; restarting starts new games."""
from dataclasses import dataclass, field
from threading import Lock
import secrets
import time

from fastapi import HTTPException, Request, Response
from app.schemas import GameState

COOKIE = "nesy_session"
TTL = 24 * 60 * 60
MAX_SESSIONS = 1000


@dataclass
class Session:
    state: GameState = field(default_factory=lambda: GameState(started_at=time.time()))
    touched: float = field(default_factory=time.monotonic)
    lock: Lock = field(default_factory=Lock)


sessions: dict[str, Session] = {}
registry_lock = Lock()


def session_for(request: Request, response: Response):
    """Serialize reads/writes per game, including commands waiting for Neural."""
    token = request.cookies.get(COOKIE)
    now = time.monotonic()
    with registry_lock:
        for key, value in list(sessions.items()):
            if now - value.touched > TTL and value.lock.acquire(blocking=False):
                try:
                    del sessions[key]
                finally:
                    value.lock.release()
        session = sessions.get(token)
        if session is None:
            if request.url.path != "/scene":
                raise HTTPException(401, "เกมหมดอายุ กรุณาโหลดหน้าเกมใหม่")
            if len(sessions) >= MAX_SESSIONS:
                raise HTTPException(503, "มีเกมใช้งานเต็ม กรุณาลองใหม่ภายหลัง")
            token = secrets.token_urlsafe(32)
            session = sessions[token] = Session()
            response.set_cookie(COOKIE, token, httponly=True, samesite="strict",
                                secure=request.url.scheme == "https", max_age=TTL)
        session.touched = now
    with session.lock:
        yield session
        session.touched = time.monotonic()
