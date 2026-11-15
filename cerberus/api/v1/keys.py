"""
API Key Management Endpoints: Creation, Listing, Revocation, and Atomic Rotation.
Enforces Granular Role-Based Access Control (RBAC requiring 'admin' scope).
"""

from datetime import UTC, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from cerberus.api.dependencies import require_scopes
from cerberus.core.database import AsyncSessionLocal
from cerberus.core.security import generate_api_key
from cerberus.models.database import ApiKeyRecord

router = APIRouter(prefix="/api/v1/keys", tags=["API Keys"])


class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name or owner of the API key")
    scopes: Optional[List[str]] = Field(
        default=["review:read", "review:write"],
        description="Granted permissions (e.g., 'review:read', 'review:write', 'admin')",
    )
    expires_in_days: Optional[int] = Field(
        default=None, ge=1, le=365, description="Key lifespan in days (null for non-expiring service keys)"
    )


class CreateApiKeyResponse(BaseModel):
    id: str
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
    name: str
    prefix: str
    scopes: List[str]
    is_active: bool
    created_at: str
    expires_at: Optional[str]


class RotateApiKeyResponse(BaseModel):
    old_key_id: str
    new_key_id: str
    name: str
    raw_key: str
    prefix: str
    scopes: List[str]
    is_active: bool
    created_at: str
    expires_at: Optional[str]
    message: str


@router.post("", response_model=CreateApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(request: CreateApiKeyRequest, _admin: str = Depends(require_scopes("admin"))):
    """
    Generate and persist a new cryptographically secure API key.
    Requires administrator authorization ('admin' scope).
    Note: The raw_key is returned only once upon creation.
    """
    raw_key, key_hash, prefix = generate_api_key(name=request.name)
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=request.expires_in_days) if request.expires_in_days else None
    scopes_str = ",".join(s.strip().lower() for s in (request.scopes or ["review:read", "review:write"]))

    async with AsyncSessionLocal() as session:
        record = ApiKeyRecord(
            name=request.name.strip(),
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
async def list_api_keys(_admin: str = Depends(require_scopes("admin"))):
    """
    List all registered API keys and metadata without exposing raw tokens or hashes.
    Requires administrator authorization ('admin' scope).
    """
    async with AsyncSessionLocal() as session:
        stmt = select(ApiKeyRecord).order_by(ApiKeyRecord.created_at.desc())
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
                name=str(r.name),
                prefix=str(r.prefix),
                scopes=scopes_list,
                is_active=bool(r.is_active),
                created_at=created_str,
                expires_at=expires_str,
            )
        )
    return items


@router.delete("/{key_id}")
async def revoke_api_key(key_id: str, _admin: str = Depends(require_scopes("admin"))):
    """
    Revoke an active API key by ID (or name fallback).
    Requires administrator authorization ('admin' scope).
    """
    async with AsyncSessionLocal() as session:
        record = await session.get(ApiKeyRecord, key_id)
        if not record:
            stmt = select(ApiKeyRecord).where(ApiKeyRecord.name == key_id)
            res = await session.execute(stmt)
            record = res.scalars().first()

        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"API Key '{key_id}' was not found.")

        record.is_active = False
        await session.commit()

    return {
        "status": "revoked",
        "key_id": record.id,
        "name": record.name,
        "message": f"API key '{record.name}' ({record.id}) has been revoked.",
    }


@router.post("/{key_id}/rotate", response_model=RotateApiKeyResponse)
async def rotate_api_key(key_id: str, _admin: str = Depends(require_scopes("admin"))):
    """
    Atomically revoke an existing API key and issue a replacement with identical scopes.
    Requires administrator authorization ('admin' scope).
    """
    async with AsyncSessionLocal() as session:
        old_record = await session.get(ApiKeyRecord, key_id)
        if not old_record:
            stmt = select(ApiKeyRecord).where(ApiKeyRecord.name == key_id)
            res = await session.execute(stmt)
            old_record = res.scalars().first()

        if not old_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"API Key '{key_id}' was not found for rotation."
            )

        # Deactivate previous key
        old_record.is_active = False

        # Generate replacement key with same identity and scopes
        raw_key, key_hash, prefix = generate_api_key(name=f"{old_record.name}")
        now = datetime.now(UTC)
        new_record = ApiKeyRecord(
            name=old_record.name,
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
        name=str(new_record.name),
        raw_key=raw_key,
        prefix=prefix,
        scopes=scopes_list,
        is_active=True,
        created_at=now.isoformat(),
        expires_at=new_record.expires_at.isoformat() if new_record.expires_at else None,
        message="Previous key was revoked; new replacement key created successfully.",
    )
