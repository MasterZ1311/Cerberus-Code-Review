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


async def get_key_record_for_token(token: Optional[str]) -> Optional[ApiKeyRecord]:
    """
    Retrieves and validates an active ApiKeyRecord from the database for the given raw token.
    Enforces active status and expiration timestamps. Returns None if invalid or expired.
    """
    if not token or not token.strip():
        return None

    token = token.strip()
    token_hash = hash_api_key(token)

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
            return None
        if key_record.expires_at is not None:
            exp = key_record.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if exp < datetime.now(UTC):
                return None
        return key_record

    if (
        settings.ENVIRONMENT.lower() not in ("production", "prod")
        and settings.DEFAULT_DEV_API_KEY
        and timing_safe_compare(token, settings.DEFAULT_DEV_API_KEY)
    ):
        return ApiKeyRecord(
            id="dev_key_id",
            name="Default Dev Key",
            tenant_id="dev_tenant",
            key_hash=token_hash,
            prefix=settings.API_KEY_PREFIX,
            scopes="review:read,review:write,admin,platform:admin",
            is_active=True,
        )

    return None


async def validate_token_against_db(token: Optional[str]) -> bool:
    """
    Validates a raw API key against stored database credentials or dev fallback.
    Returns True if valid and active, False otherwise.
    """
    return (await get_key_record_for_token(token)) is not None


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
        tenant_id = (key_record.tenant_id or "").strip()
        if not tenant_id:
            if settings.ENVIRONMENT.lower() in ("production", "prod"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"error": "unowned_api_key", "message": "API key lacks an explicit tenant identity."},
                )
            tenant_id = "dev_tenant"
    else:
        tenant_id = "dev_tenant"
        scopes_set = {"review:read", "review:write", "admin", "platform:admin"}

    is_dev_mode = settings.ENVIRONMENT.lower() not in ("production", "prod")
    is_platform_admin = ("platform:admin" in scopes_set) or (
        is_dev_mode and settings.DEFAULT_DEV_API_KEY and timing_safe_compare(token, settings.DEFAULT_DEV_API_KEY)
    )

    request.state.api_key_record = key_record
    request.state.api_key_scopes = scopes_set
    request.state.tenant_id = tenant_id
    request.state.is_platform_admin = is_platform_admin

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
    Plain 'admin' is tenant-scoped and NEVER satisfies 'platform:admin'.
    'platform:admin' satisfies both platform-wide and tenant-scoped requirements.
    """

    async def _scope_checker(request: Request, token: str = Depends(verify_api_key)) -> str:
        granted_scopes: set[str] = getattr(request.state, "api_key_scopes", set())
        is_platform_admin: bool = getattr(request.state, "is_platform_admin", False) or (
            "platform:admin" in granted_scopes
        )

        for rs in required_scopes:
            rs_lower = rs.lower().strip()
            if rs_lower == "platform:admin":
                if not is_platform_admin:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "error": "insufficient_scope",
                            "message": f"Permission denied: Missing required scope '{rs}'",
                            "required_scopes": list(required_scopes),
                            "granted_scopes": sorted(list(granted_scopes)),
                        },
                    )
            else:
                # For tenant scopes ('admin', 'review:read', 'review:write')
                # platform:admin can access anything; 'admin' satisfies any tenant-level scope
                if not (is_platform_admin or ("admin" in granted_scopes) or (rs_lower in granted_scopes)):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "error": "insufficient_scope",
                            "message": f"Permission denied: Missing required scope '{rs}'",
                            "required_scopes": list(required_scopes),
                            "granted_scopes": sorted(list(granted_scopes)),
                        },
                    )
        return token

    return _scope_checker
