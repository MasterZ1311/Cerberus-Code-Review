"""
Enterprise JWT (JSON Web Token) Implementation for cerberus</>.
Cryptographically secure HMAC-SHA256 token creation, signing, and verification
with zero external dependencies.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, List, Optional, Set

from cerberus.config import settings


class JWTError(Exception):
    """Base exception for all JWT operations."""

    pass


class ExpiredSignatureError(JWTError):
    """Raised when a token's expiration timestamp has passed."""

    pass


class InvalidTokenError(JWTError):
    """Raised when token structure, signature, or claims are malformed."""

    pass


def _base64url_encode(data: bytes) -> str:
    """Encodes bytes into URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _base64url_decode(data: str) -> bytes:
    """Decodes URL-safe base64 string, restoring padding as needed."""
    rem = len(data) % 4
    if rem > 0:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data.encode("utf-8"))


class JWTManager:
    """Manages creation, signing, and cryptographic verification of JWTs."""

    def __init__(self, secret_key: Optional[str] = None, algorithm: str = "HS256", issuer: str = "cerberus-ai"):
        self.secret_key = (secret_key or settings.SECRET_KEY).encode("utf-8")
        self.algorithm = algorithm
        self.issuer = issuer

    def create_token(
        self,
        subject: str,
        tenant_id: str = "default",
        scopes: Optional[List[str] | Set[str] | str] = None,
        token_type: str = "access",  # nosec B107
        expires_in_seconds: int = 3600,
        extra_claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Creates and signs a new JWT with standard RFC 7519 claims.
        """
        now = int(time.time())
        exp = now + expires_in_seconds

        if isinstance(scopes, (list, set)):
            scopes_str = ",".join(sorted(str(s).strip() for s in scopes))
        elif isinstance(scopes, str):
            scopes_str = scopes.strip()
        else:
            scopes_str = "review:read,review:write"

        header = {"alg": self.algorithm, "typ": "JWT"}
        payload: Dict[str, Any] = {
            "sub": subject,
            "tenant_id": tenant_id,
            "scopes": scopes_str,
            "type": token_type,
            "iss": self.issuer,
            "iat": now,
            "nbf": now,
            "exp": exp,
        }
        if extra_claims:
            payload.update(extra_claims)

        header_b64 = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_b64}.{payload_b64}".encode()

        signature = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()
        signature_b64 = _base64url_encode(signature)

        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def decode_and_verify(self, token: str) -> Dict[str, Any]:
        """
        Verifies signature, structure, and expiration of a JWT.
        Returns the decoded payload claims dict.
        """
        if not token or not isinstance(token, str):
            raise InvalidTokenError("Token must be a non-empty string")

        parts = token.strip().split(".")
        if len(parts) != 3:
            raise InvalidTokenError("Invalid JWT token format; expected 3 dot-separated segments")

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature in constant time
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()
        try:
            provided_sig = _base64url_decode(signature_b64)
        except Exception as e:
            raise InvalidTokenError(f"Malformed signature encoding: {e}") from e

        if not hmac.compare_digest(expected_sig, provided_sig):
            raise InvalidTokenError("Invalid token signature")

        # Decode header and verify algorithm
        try:
            header = json.loads(_base64url_decode(header_b64).decode("utf-8"))
            if header.get("alg") != self.algorithm:
                raise InvalidTokenError(f"Unsupported algorithm '{header.get('alg')}'; expected '{self.algorithm}'")
        except Exception as e:
            raise InvalidTokenError(f"Malformed token header: {e}") from e

        # Decode payload and verify claims
        try:
            payload = json.loads(_base64url_decode(payload_b64).decode("utf-8"))
        except Exception as e:
            raise InvalidTokenError(f"Malformed token payload: {e}") from e

        now = int(time.time())
        exp = payload.get("exp")
        if exp is not None and isinstance(exp, (int, float)):
            if now > exp:
                raise ExpiredSignatureError(f"Token expired {now - int(exp)} seconds ago")

        nbf = payload.get("nbf")
        if nbf is not None and isinstance(nbf, (int, float)):
            if now < nbf:
                raise InvalidTokenError("Token is not yet valid (nbf claim)")

        return payload


# Global singleton instance
jwt_manager = JWTManager()
JWT_SECRET = settings.SECRET_KEY


def create_jwt_token(
    payload: Dict[str, Any],
    expires_delta_seconds: int = 3600,
    secret_key: Optional[str] = None,
) -> str:
    """Convenience function to create a signed JWT token from a payload dict."""
    mgr = JWTManager(secret_key=secret_key) if secret_key else jwt_manager
    sub = str(payload.get("sub", "anonymous"))
    tenant_id = str(payload.get("tenant_id", "default"))
    scopes = payload.get("scopes", "review:read,review:write")
    token_type = str(payload.get("type", "access"))
    extra = {
        k: v for k, v in payload.items() if k not in ("sub", "tenant_id", "scopes", "type", "exp", "iat", "iss", "nbf")
    }
    return mgr.create_token(
        subject=sub,
        tenant_id=tenant_id,
        scopes=scopes,
        token_type=token_type,
        expires_in_seconds=expires_delta_seconds,
        extra_claims=extra,
    )


def verify_jwt_token(token: str, secret_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Convenience function to verify a JWT token. Returns payload dict, or None if invalid/expired."""
    try:
        mgr = JWTManager(secret_key=secret_key) if secret_key else jwt_manager
        return mgr.decode_and_verify(token)
    except (JWTError, Exception):
        return None


def generate_api_key_jwt(tenant_id: str = "default", role: str = "admin", expires_days: int = 30) -> str:
    """Generates an enterprise-grade long-lived API key encoded as a JWT token."""
    return create_jwt_token(
        payload={"sub": f"api_key_{tenant_id}", "tenant_id": tenant_id, "role": role},
        expires_delta_seconds=expires_days * 86400,
    )


def create_refresh_token(tenant_id: str = "default", user_id: str = "default_user") -> str:
    """Generates a 30-day refresh token for rotating access tokens."""
    return create_jwt_token(
        payload={"sub": user_id, "tenant_id": tenant_id, "type": "refresh"},
        expires_delta_seconds=30 * 86400,
    )
