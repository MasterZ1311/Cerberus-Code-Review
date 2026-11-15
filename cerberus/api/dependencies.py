"""
FastAPI Dependencies for Authentication, Database Sessions, and Rate Limiting.
"""

from datetime import UTC, datetime
from typing import Callable, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select

from cerberus.config import settings
from cerberus.core.database import AsyncSessionLocal
from cerberus.core.security import hash_api_key, rate_limiter, timing_safe_compare
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
                exp = exp.replace(tzinfo=UTC)
            if exp < datetime.now(UTC):
                return False
        return True

    if (
        settings.ENVIRONMENT.lower() not in ("production", "prod")
        and settings.DEFAULT_DEV_API_KEY
        and timing_safe_compare(token, settings.DEFAULT_DEV_API_KEY)
    ):
        return True

    return False


async def verify_api_key(request: Request, authorization: Optional[str] = Header(None)) -> str:
    """
    Validates the API key from the Authorization header.
    Requires genuine cryptographic validation against active database credentials.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_authentication", "message": "No Authorization header provided"},
        )

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token_format", "message": "Authorization must be Bearer <token>"},
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
                detail={"error": "invalid_api_key", "message": "API key is inactive or revoked"},
            )
        if key_record.expires_at is not None:
            exp = key_record.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if exp < datetime.now(UTC):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"error": "invalid_api_key", "message": "API key is invalid or has expired"},
                )
    else:
        # In non-production mode, provide fallback check for settings.DEFAULT_DEV_API_KEY if DB seed was not present
        if (
            settings.ENVIRONMENT.lower() not in ("production", "prod")
            and settings.DEFAULT_DEV_API_KEY
            and timing_safe_compare(token, settings.DEFAULT_DEV_API_KEY)
        ):
            scopes_set = {"review:read", "review:write", "admin"}
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_api_key", "message": "API key is invalid or has expired"},
            )

    if key_record is not None:
        scopes_str = key_record.scopes if key_record.scopes else "review:read,review:write"
        scopes_set = {s.strip().lower() for s in scopes_str.split(",") if s.strip()}
        tenant_id = key_record.tenant_id or key_record.id or "default_tenant"
    else:
        tenant_id = "default_dev_tenant"
    request.state.api_key_record = key_record
    request.state.api_key_scopes = scopes_set
    request.state.tenant_id = tenant_id

    # Check Rate Limit (distributed Redis with automatic in-memory fallback)
    allowed, remaining, retry_after = await rate_limiter.is_allowed_async(token)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limit_exceeded", "message": f"Rate limit exceeded. Retry in {retry_after}s."},
            headers={"Retry-After": str(retry_after)},
        )

    return token


def require_scopes(*required_scopes: str) -> Callable:
    """
    Dependency factory enforcing granular Role-Based Access Control (RBAC).
    Verifies that the authenticated API key possesses all required scopes.
    """

    async def _scope_checker(request: Request, token: str = Depends(verify_api_key)) -> str:
        granted_scopes: set[str] = getattr(request.state, "api_key_scopes", set())
        if "admin" in granted_scopes:
            return token
        for rs in required_scopes:
            if rs.lower() not in granted_scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "insufficient_scope",
                        "message": f"Permission denied: Missing required scope '{rs}'",
                        "required_scopes": list(required_scopes),
                        "granted_scopes": list(granted_scopes),
                    },
                )
        return token

    return _scope_checker
