"""JWT authentication helpers for the API Gateway.

Provides token creation and verification utilities, plus the hardcoded
demo user. The demo user will be replaced with database-backed auth
in a future iteration.
"""
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
"""OAuth2 password bearer scheme utilizing token URL path /auth/token."""

DEMO_USER = {"username": "admin", "password": "aura2026"}
"""Default hardcoded credentials dictionary for user authentication demo."""

def create_token(username: str) -> str:
    """Generates a signed JWT access token for a given user.

    Args:
        username: Subject name to encode in the token.

    Returns:
        Encoded HS256 JWT token string.
    """
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.access_token_expire_minutes)
    return jwt.encode({"sub": username, "exp": exp}, s.secret_key, algorithm="HS256")

def verify_token(token: str = Depends(oauth2_scheme)) -> str:
    """Verifies a JWT access token and extracts the subject username.

    Args:
        token: Incoming JWT token string.

    Returns:
        The extracted username subject.

    Raises:
        HTTPException: If token verification fails (status 401).
    """
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        return payload["sub"]
    except JWTError:
        raise HTTPException(401, "Invalid token")

