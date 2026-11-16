"""
API Key Management Endpoints: Creation, Listing, Revocation, and Atomic Rotation.
Enforces Granular Role-Based Access Control (RBAC requiring 'admin' scope).
"""

from datetime import UTC, datetime, timedelta
from typing import Any, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from cerberus.api.dependencies import require_scopes
from cerberus.core.database import AsyncSessionLocal
from cerberus.core.security import generate_api_key
from cerberus.models.database import ApiKeyRecord

router = APIRouter(prefix="/api/v1/keys", tags=["API Keys"])

ALLOWED_TENANT_SCOPES: Set[str] = {"review:read", "review:write", "admin"}
ALLOWED_PLATFORM_SCOPES: Set[str] = {"platform:admin"}
ALL_VALID_SCOPES: Set[str] = ALLOWED_TENANT_SCOPES | ALLOWED_PLATFORM_SCOPES


class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name or owner of the API key")
    tenant_id: Optional[str] = Field(
        default=None,
        description="Explicit tenant identifier. Non-platform admins can only create keys for their own tenant.",
    )
    scopes: Optional[List[str]] = Field(
        default=["review:read", "review:write"],
        description="Granted permissions (e.g., 'review:read', 'review:write', 'admin', 'platform:admin')",
    )
    expires_in_days: Optional[int] = Field(
        default=None, ge=1, le=365, description="Key lifespan in days (null for non-expiring service keys)"
    )


class CreateApiKeyResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    raw_key: str
    prefix: str
    scopes: List[str]
    is_active: bool
    created_at: str
    expires_at: Optional[str]
    message: str


class ApiKeySummaryResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    prefix: str
    scopes: List[str]
    is_active: bool
    created_at: str
    expires_at: Optional[str]


class RotateApiKeyResponse(BaseModel):
    old_key_id: str
    new_key_id: str
    tenant_id: str
    name: str
    raw_key: str
    prefix: str
    scopes: List[str]
    is_active: bool
    created_at: str
    expires_at: Optional[str]
    message: str


@router.post("", response_model=CreateApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: CreateApiKeyRequest,
    http_req: Request,
    _admin: str = Depends(require_scopes("admin")),
):
    """
    Generate and persist a new cryptographically secure API key.
    Requires administrator authorization ('admin' scope). Key creation is tenant-scoped by default.
    Platform administrators with 'platform:admin' scope can explicitly provision keys for other tenants.
    Note: The raw_key is returned only once upon creation.
    """
    caller_tenant = getattr(http_req.state, "tenant_id", "default")
    is_platform_admin = getattr(http_req.state, "is_platform_admin", False)
    caller_scopes: Set[str] = set(getattr(http_req.state, "api_key_scopes", set()))

    # Validate and normalize requested scopes
    requested_scopes = [s.strip().lower() for s in (request.scopes or ["review:read", "review:write"]) if s.strip()]
    for s in requested_scopes:
        if s not in ALL_VALID_SCOPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scope '{s}'. Allowed scopes are: {sorted(list(ALL_VALID_SCOPES))}",
            )

    if not is_platform_admin:
        # Tenant admin boundary enforcement:
        if request.tenant_id and request.tenant_id.strip() != caller_tenant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: Only platform administrators can provision API keys for other tenants.",
            )
        # Cannot mint platform:admin
        if "platform:admin" in requested_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: Tenant administrators cannot mint 'platform:admin' scoped keys.",
            )
        # Cannot delegate scopes caller does not already hold
        for s in requested_scopes:
            if s not in caller_scopes and "admin" not in caller_scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: Cannot grant scope '{s}' which the caller does not hold.",
                )
        assigned_tenant = caller_tenant
    else:
        assigned_tenant = (
            request.tenant_id.strip() if (request.tenant_id and request.tenant_id.strip()) else caller_tenant
        )

    raw_key, key_hash, prefix = generate_api_key(name=request.name)
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=request.expires_in_days) if request.expires_in_days else None
    scopes_str = ",".join(requested_scopes)

    async with AsyncSessionLocal() as session:
        record = ApiKeyRecord(
            name=request.name.strip(),
            tenant_id=assigned_tenant,
            key_hash=key_hash,
            prefix=prefix,
            scopes=scopes_str,
            is_active=True,
            created_at=now,
            expires_at=expires_at,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        key_id = record.id

    return CreateApiKeyResponse(
        id=str(key_id),
        tenant_id=assigned_tenant,
        name=request.name.strip(),
        raw_key=raw_key,
        prefix=prefix,
        scopes=[s.strip() for s in scopes_str.split(",") if s.strip()],
        is_active=True,
        created_at=now.isoformat(),
        expires_at=expires_at.isoformat() if expires_at else None,
        message="Store this key securely. The raw token will not be shown again.",
    )


@router.get("", response_model=List[ApiKeySummaryResponse])
async def list_api_keys(
    http_req: Request,
    tenant_id: Optional[str] = Query(None, description="Optional tenant filter (platform admins only)"),
    _admin: str = Depends(require_scopes("admin")),
):
    """
    List registered API keys and metadata without exposing raw tokens or hashes.
    Tenant-scoped by default: tenant administrators only view keys belonging to their own tenant.
    Platform administrators ('platform:admin') can view all keys or filter by tenant_id.
    """
    caller_tenant = getattr(http_req.state, "tenant_id", "default")
    is_platform_admin = getattr(http_req.state, "is_platform_admin", False)

    if not is_platform_admin and tenant_id and tenant_id.strip() != caller_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Only platform administrators can filter API keys by other tenants.",
        )

    async with AsyncSessionLocal() as session:
        if is_platform_admin:
            if tenant_id:
                stmt = (
                    select(ApiKeyRecord)
                    .where(ApiKeyRecord.tenant_id == tenant_id)
                    .order_by(ApiKeyRecord.created_at.desc())
                )
            else:
                stmt = select(ApiKeyRecord).order_by(ApiKeyRecord.created_at.desc())
        else:
            stmt = (
                select(ApiKeyRecord)
                .where(ApiKeyRecord.tenant_id == caller_tenant)
                .order_by(ApiKeyRecord.created_at.desc())
            )

        result = await session.execute(stmt)
        records = result.scalars().all()

    items = []
    for r in records:
        scopes_list = [s.strip() for s in (r.scopes or "").split(",") if s.strip()]
        created_str = r.created_at.isoformat() if r.created_at else ""
        expires_str = r.expires_at.isoformat() if r.expires_at else None
        items.append(
            ApiKeySummaryResponse(
                id=str(r.id),
                tenant_id=str(r.tenant_id or "default"),
                name=str(r.name),
                prefix=str(r.prefix),
                scopes=scopes_list,
                is_active=bool(r.is_active),
                created_at=created_str,
                expires_at=expires_str,
            )
        )
    return items


async def _get_tenant_scoped_api_key(
    session: Any,
    key_id: str,
    caller_tenant: str,
    is_platform_admin: bool,
    action_description: str = "access",
) -> ApiKeyRecord:
    """Retrieves an ApiKeyRecord by ID or name, enforcing multi-tenant isolation."""
    record = await session.get(ApiKeyRecord, key_id)
    if not record:
        stmt = select(ApiKeyRecord).where(ApiKeyRecord.name == key_id)
        res = await session.execute(stmt)
        record = res.scalars().first()

    if not record or (not is_platform_admin and record.tenant_id != caller_tenant):
        detail = (
            f"API Key '{key_id}' was not found for {action_description}."
            if action_description != "access"
            else f"API Key '{key_id}' was not found."
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

    return record


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: str,
    http_req: Request,
    _admin: str = Depends(require_scopes("admin")),
):
    """
    Revoke an active API key by ID (or name fallback).
    Enforces tenant scoping: tenant admins can only revoke their own tenant's keys.
    """
    caller_tenant = getattr(http_req.state, "tenant_id", "default")
    is_platform_admin = getattr(http_req.state, "is_platform_admin", False)

    async with AsyncSessionLocal() as session:
        record = await _get_tenant_scoped_api_key(session, key_id, caller_tenant, is_platform_admin)
        rec_scopes = {s.strip().lower() for s in (record.scopes or "").split(",") if s.strip()}
        if not is_platform_admin and "platform:admin" in rec_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: Tenant administrators cannot revoke platform administrator keys.",
            )
        record.is_active = False
        await session.commit()

    return {
        "status": "revoked",
        "key_id": record.id,
        "tenant_id": record.tenant_id,
        "name": record.name,
        "message": f"API key '{record.name}' ({record.id}) has been revoked.",
    }


@router.post("/{key_id}/rotate", response_model=RotateApiKeyResponse)
async def rotate_api_key(
    key_id: str,
    http_req: Request,
    _admin: str = Depends(require_scopes("admin")),
):
    """
    Atomically revoke an existing API key and issue a replacement with identical scopes and tenant identity.
    Preserves tenant identity unconditionally upon rotation.
    """
    caller_tenant = getattr(http_req.state, "tenant_id", "default")
    is_platform_admin = getattr(http_req.state, "is_platform_admin", False)
    caller_scopes: Set[str] = set(getattr(http_req.state, "api_key_scopes", set()))

    async with AsyncSessionLocal() as session:
        old_record = await _get_tenant_scoped_api_key(
            session, key_id, caller_tenant, is_platform_admin, action_description="rotation"
        )

        old_scopes = {s.strip().lower() for s in (old_record.scopes or "").split(",") if s.strip()}
        if not is_platform_admin:
            if "platform:admin" in old_scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied: Tenant administrators cannot rotate platform administrator keys.",
                )
            for s in old_scopes:
                if s not in caller_scopes and "admin" not in caller_scopes:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Permission denied: Cannot rotate key possessing unheld scope '{s}'.",
                    )

        # Deactivate previous key
        old_record.is_active = False

        # Generate replacement key with same identity, scopes, and tenant identity
        raw_key, key_hash, prefix = generate_api_key(name=f"{old_record.name}")
        now = datetime.now(UTC)
        new_record = ApiKeyRecord(
            name=old_record.name,
            tenant_id=old_record.tenant_id,  # Unconditionally preserve tenant identity
            key_hash=key_hash,
            prefix=prefix,
            scopes=old_record.scopes,
            is_active=True,
            created_at=now,
            expires_at=old_record.expires_at,
        )
        session.add(new_record)
        await session.commit()
        await session.refresh(new_record)

    scopes_list = [s.strip() for s in (new_record.scopes or "").split(",") if s.strip()]
    return RotateApiKeyResponse(
        old_key_id=str(old_record.id),
        new_key_id=str(new_record.id),
        tenant_id=str(new_record.tenant_id),
        name=str(new_record.name),
        raw_key=raw_key,
        prefix=prefix,
        scopes=scopes_list,
        is_active=True,
        created_at=now.isoformat(),
        expires_at=new_record.expires_at.isoformat() if new_record.expires_at else None,
        message="Previous key was revoked; new replacement key created successfully with preserved tenant identity.",
    )
