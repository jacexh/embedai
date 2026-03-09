"""JWT authentication dependencies — compatible with the Go gateway token format."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

_bearer = HTTPBearer()


@dataclass
class CurrentUser:
    user_id: str
    project_id: str
    role: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> CurrentUser:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    user_id = payload.get("user_id")
    project_id = payload.get("project_id")
    role = payload.get("role")
    if not user_id or not project_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token claims")

    return CurrentUser(user_id=user_id, project_id=project_id, role=role)


def create_stream_token(episode_id: str, expires_in: int = 3600) -> str:
    """Generate a short-lived token granting read access to a specific episode stream."""
    import time

    payload = {
        "sub": episode_id,
        "type": "stream",
        "exp": int(time.time()) + expires_in,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
