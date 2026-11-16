"""
OAuth2 & JWT Session Authentication Router for cerberus</>.
Provides token generation, OAuth2 authorization flows, token refreshing, and identity introspection.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from cerberus.api.dependencies import get_key_record_for_token, verify_api_key
from cerberus.config import settings
from cerberus.core.jwt_auth import ExpiredSignatureError, InvalidTokenError, jwt_manager

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & OAuth2"])


class TokenRequest(BaseModel):
    """Payload to exchange credentials or API key for a JWT session token."""

    grant_type: str = Field(default="api_key", description="Grant type ('api_key' or 'client_credentials')")
    api_key: Optional[str] = Field(default=None, description="Raw Cerberus API key")
    username: Optional[str] = Field(default=None, description="Username for user login")
    password: Optional[str] = Field(default=None, description="Password for user login")
    tenant_id: Optional[str] = Field(default="default", description="Target tenant organization")
    requested_scopes: Optional[str] = Field(default=None, description="Optional subset of scopes requested")


class TokenResponse(BaseModel):
    """OAuth2 standard token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    tenant_id: str
    scopes: str


class RefreshRequest(BaseModel):
    """Payload to refresh an access token."""

    refresh_token: str


@router.post("/token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def create_session_token(payload: TokenRequest) -> TokenResponse:
    """
    Exchanges an API key or credentials for a short-lived cryptographic JWT access token
    and refresh token.
    """
    subject: str = "service"
    tenant_id: str = payload.tenant_id or "default"
    effective_scopes: str = "review:read,review:write"

    if payload.grant_type == "api_key" or payload.api_key:
        raw_key = payload.api_key
        if not raw_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "missing_api_key", "message": "Field 'api_key' is required for api_key grant"},
            )

        key_record = await get_key_record_for_token(raw_key)
        if not key_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_api_key", "message": "Provided API key is invalid or inactive"},
            )

        subject = key_record.name or f"key_{key_record.id}"
        tenant_id = key_record.tenant_id or tenant_id
        effective_scopes = key_record.scopes or effective_scopes

    elif payload.grant_type in ("password", "client_credentials"):
        # Basic developer/admin login validation
        if not payload.username or not payload.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_credentials", "message": "Username and password are required"},
            )

        is_dev = settings.ENVIRONMENT.lower() not in ("production", "prod")
        if (
            is_dev
            and payload.username == "admin"
            and payload.password in ("admin", settings.SECRET_KEY, settings.DEFAULT_DEV_API_KEY)
        ):
            subject = "admin"
            tenant_id = "platform"
            effective_scopes = "review:read,review:write,admin,platform:admin"
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_credentials", "message": "Invalid username or password"},
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "unsupported_grant_type", "message": f"Grant type '{payload.grant_type}' is unsupported"},
        )

    # Filter by requested scopes if provided
    if payload.requested_scopes:
        held_scopes = {s.strip().lower() for s in effective_scopes.split(",") if s.strip()}
        req_scopes = {s.strip().lower() for s in payload.requested_scopes.split(",") if s.strip()}
        if not req_scopes.issubset(held_scopes):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "scope_escalation_rejected", "message": "Requested scopes exceed credentials"},
            )
        effective_scopes = ",".join(sorted(req_scopes))

    access_exp = 3600  # 1 hour
    refresh_exp = 86400 * 7  # 7 days

    access_token = jwt_manager.create_token(
        subject=subject,
        tenant_id=tenant_id,
        scopes=effective_scopes,
        token_type="access",  # nosec B106
        expires_in_seconds=access_exp,
    )
    refresh_token = jwt_manager.create_token(
        subject=subject,
        tenant_id=tenant_id,
        scopes=effective_scopes,
        token_type="refresh",  # nosec B106
        expires_in_seconds=refresh_exp,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",  # nosec B106
        expires_in=access_exp,
        refresh_token=refresh_token,
        tenant_id=tenant_id,
        scopes=effective_scopes,
    )


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh_access_token(payload: RefreshRequest) -> TokenResponse:
    """Refreshes an expired JWT access token using a valid refresh token."""
    try:
        claims = jwt_manager.decode_and_verify(payload.refresh_token)
    except ExpiredSignatureError as ese:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "refresh_token_expired",
                "message": "Refresh token has expired; please authenticate again",
            },
        ) from ese
    except InvalidTokenError as ite:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_refresh_token", "message": str(ite)},
        ) from ite

    if claims.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_token_type", "message": "Provided token is not a refresh token"},
        )

    subject = str(claims.get("sub", "service"))
    tenant_id = str(claims.get("tenant_id", "default"))
    scopes = str(claims.get("scopes", "review:read,review:write"))

    access_exp = 3600
    access_token = jwt_manager.create_token(
        subject=subject,
        tenant_id=tenant_id,
        scopes=scopes,
        token_type="access",  # nosec B106
        expires_in_seconds=access_exp,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",  # nosec B106
        expires_in=access_exp,
        refresh_token=payload.refresh_token,
        tenant_id=tenant_id,
        scopes=scopes,
    )


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_current_identity(
    request: Request,
    token: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Returns the authenticated identity, tenant, and active RBAC scopes."""
    jwt_claims = getattr(request.state, "jwt_payload", None)
    key_record = getattr(request.state, "api_key_record", None)
    scopes = list(getattr(request.state, "api_key_scopes", set()))
    tenant_id = getattr(request.state, "tenant_id", "default")
    is_platform_admin = getattr(request.state, "is_platform_admin", False)

    return {
        "status": "authenticated",
        "auth_type": "jwt" if jwt_claims else "api_key",
        "subject": jwt_claims.get("sub") if jwt_claims else (key_record.name if key_record else "default"),
        "tenant_id": tenant_id,
        "scopes": scopes,
        "is_platform_admin": is_platform_admin,
    }


@router.get("/oauth/{provider}/authorize", status_code=status.HTTP_200_OK)
async def get_oauth_authorization_url(provider: str, redirect_uri: str) -> Dict[str, Any]:
    """Generates OAuth2 authorization URL for SSO identity providers."""
    prov = provider.lower()
    if prov not in ("google", "github", "gitlab"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "unsupported_provider", "message": f"Provider '{provider}' is not supported"},
        )

    client_id = getattr(settings, f"{prov.upper()}_CLIENT_ID", None) or f"mock_{prov}_client_id"
    if prov == "google":
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={client_id}&response_type=code&scope=openid%20email%20profile&redirect_uri={redirect_uri}"
        )
    elif prov == "gitlab":
        auth_url = (
            f"https://gitlab.com/oauth/authorize?"
            f"client_id={client_id}&response_type=code&scope=read_user%20openid&redirect_uri={redirect_uri}"
        )
    else:
        auth_url = (
            f"https://github.com/login/oauth/authorize?"
            f"client_id={client_id}&scope=user:email%20read:org&redirect_uri={redirect_uri}"
        )

    return {
        "provider": prov,
        "authorization_url": auth_url,
        "redirect_uri": redirect_uri,
        "status": "ready",
    }
