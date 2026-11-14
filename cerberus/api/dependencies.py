"""
FastAPI Dependencies for Authentication, Database Sessions, and Rate Limiting.
"""

from datetime import datetime, timezone
from typing import Optional
from fastapi import Header, HTTPException, Request, status
from sqlalchemy import select
from cerberus.config import settings
from cerberus.core.database import AsyncSessionLocal
from cerberus.core.security import hash_api_key, rate_limiter
from cerberus.models.database import ApiKeyRecord


async def validate_token_against_db(token: Optional[str]) -> bool:
    """
    Validates a raw API key against stored database credentials or dev fallback.
    Returns True if valid and active, False otherwise.
    """
    if not token or not token.strip():
        return False

    token = token.strip()
    token_hash = hash_api_key(token)

    try:
        async with AsyncSessionLocal() as session:
            stmt = select(ApiKeyRecord).where(ApiKeyRecord.key_hash == token_hash)
            result = await session.execute(stmt)
            key_record = result.scalars().first()
    except Exception:
        key_record = None

    if key_record is not None:
        if not key_record.is_active:
            return False
        if key_record.expires_at is not None:
            exp = key_record.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < datetime.now(timezone.utc):
                return False
        return True

    if (
        settings.ENVIRONMENT.lower() == "development"
        and settings.DEFAULT_DEV_API_KEY
        and token == settings.DEFAULT_DEV_API_KEY
    ):
        return True

    return False


async def verify_api_key(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> str:
    """
    Validates the API key from the Authorization header.
    Requires genuine cryptographic validation against active database credentials.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_authentication", "message": "No Authorization header provided"}
        )

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token_format", "message": "Authorization must be Bearer <token>"}
        )

    token = parts[1].strip()
    token_hash = hash_api_key(token)

    # Query ApiKeyRecord from database via AsyncSessionLocal
    key_record: Optional[ApiKeyRecord] = None
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(ApiKeyRecord).where(ApiKeyRecord.key_hash == token_hash)
            result = await session.execute(stmt)
            key_record = result.scalars().first()
    except Exception:
        key_record = None

    if key_record is not None:
        if not key_record.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_api_key", "message": "API key is inactive or revoked"}
            )
        if key_record.expires_at is not None:
            exp = key_record.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"error": "invalid_api_key", "message": "API key is invalid or has expired"}
                )
    else:
        # In development mode, provide fallback check for settings.DEFAULT_DEV_API_KEY if DB seed was not present
        if (
            settings.ENVIRONMENT.lower() == "development"
            and settings.DEFAULT_DEV_API_KEY
            and token == settings.DEFAULT_DEV_API_KEY
        ):
            pass
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_api_key", "message": "API key is invalid or has expired"}
            )

    # Check Rate Limit (distributed Redis with automatic in-memory fallback)
    allowed, remaining, retry_after = await rate_limiter.is_allowed_async(token)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limit_exceeded", "message": f"Rate limit exceeded. Retry in {retry_after}s."},
            headers={"Retry-After": str(retry_after)}
        )

    return token
