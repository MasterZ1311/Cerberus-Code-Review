"""
Tests for Enterprise JWT Authentication and OAuth2 Providers.
"""

from fastapi.testclient import TestClient

from cerberus.api.app import app
from cerberus.core.jwt_auth import (
    create_jwt_token,
    create_refresh_token,
    generate_api_key_jwt,
    verify_jwt_token,
)


def test_create_and_verify_jwt_token():
    payload = {"sub": "user_123", "role": "lead_architect", "tenant_id": "corp_alpha"}
    token = create_jwt_token(payload, expires_delta_seconds=3600)
    assert isinstance(token, str)
    assert token.count(".") == 2

    # Verify token
    verified = verify_jwt_token(token)
    assert verified is not None
    assert verified["sub"] == "user_123"
    assert verified["role"] == "lead_architect"
    assert verified["tenant_id"] == "corp_alpha"
    assert "exp" in verified
    assert "iat" in verified


def test_expired_jwt_token():
    payload = {"sub": "user_expired"}
    token = create_jwt_token(payload, expires_delta_seconds=-10)  # already expired
    assert verify_jwt_token(token) is None


def test_tampered_jwt_token():
    payload = {"sub": "user_legit"}
    token = create_jwt_token(payload)
    parts = token.split(".")
    tampered_token = f"{parts[0]}.eyJhZG1pbiI6IHRydWV9.{parts[2]}"
    assert verify_jwt_token(tampered_token) is None


def test_invalid_signature_secret():
    payload = {"sub": "user_spoofed"}
    token = create_jwt_token(payload, secret_key="wrong_secret_key_1234567890")
    assert verify_jwt_token(token, secret_key="expected_secret_key_0987654321") is None


def test_generate_api_key_jwt_and_refresh_token():
    token = generate_api_key_jwt(tenant_id="tenant_x", role="admin", expires_days=7)
    verified = verify_jwt_token(token)
    assert verified is not None
    assert verified["tenant_id"] == "tenant_x"
    assert verified["role"] == "admin"

    refresh_token = create_refresh_token(tenant_id="tenant_x", user_id="user_x")
    ref_verified = verify_jwt_token(refresh_token)
    assert ref_verified is not None
    assert ref_verified["type"] == "refresh"
    assert ref_verified["sub"] == "user_x"


def test_auth_api_endpoints():
    client = TestClient(app)

    # 1. Issue token via POST /api/v1/auth/token using api_key grant
    req_body = {
        "grant_type": "api_key",
        "api_key": "cvai_dev_key_123",
        "tenant_id": "test_tenant",
    }
    res_token = client.post("/api/v1/auth/token", json=req_body)
    assert res_token.status_code == 200
    token_data = res_token.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"

    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]

    # 2. Check current identity via GET /api/v1/auth/me with Bearer token
    res_me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert res_me.status_code == 200
    me_data = res_me.json()
    assert me_data["status"] == "authenticated"
    assert me_data["auth_type"] == "jwt"
    assert "tenant_id" in me_data
    assert isinstance(me_data["scopes"], list)

    # 3. Refresh token via POST /api/v1/auth/refresh
    res_ref = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert res_ref.status_code == 200
    ref_data = res_ref.json()
    assert "access_token" in ref_data
    assert ref_data["token_type"] == "bearer"

    # 4. OAuth Authorize Redirect URLs
    for provider in ["github", "gitlab", "google"]:
        res_oauth = client.get(f"/api/v1/auth/oauth/{provider}/authorize?redirect_uri=https://app.cerberus.io/callback")
        assert res_oauth.status_code == 200
        oauth_data = res_oauth.json()
        assert oauth_data["provider"] == provider
        assert "authorization_url" in oauth_data
        assert "redirect_uri=" in oauth_data["authorization_url"]

    # 5. Unsupported OAuth provider -> 400
    res_bad_oauth = client.get("/api/v1/auth/oauth/unknown/authorize?redirect_uri=https://app.cerberus.io/callback")
    assert res_bad_oauth.status_code == 400


def test_auth_edge_cases_and_error_handling():
    client = TestClient(app)

    # Missing api_key when requested
    res = client.post("/api/v1/auth/token", json={"grant_type": "api_key", "api_key": ""})
    assert res.status_code == 400

    # Invalid api_key
    res = client.post("/api/v1/auth/token", json={"grant_type": "api_key", "api_key": "invalid_key_xyz"})
    assert res.status_code == 401

    # Unsupported grant type
    res = client.post("/api/v1/auth/token", json={"grant_type": "invalid_grant"})
    assert res.status_code == 400

    # Password grant missing credentials
    res = client.post("/api/v1/auth/token", json={"grant_type": "password"})
    assert res.status_code == 400

    # Password grant invalid credentials
    res = client.post("/api/v1/auth/token", json={"grant_type": "password", "username": "bad", "password": "bad"})
    assert res.status_code == 401

    # Password grant valid dev/admin credentials
    res = client.post("/api/v1/auth/token", json={"grant_type": "password", "username": "admin", "password": "admin"})
    assert res.status_code == 200
    admin_token = res.json()["access_token"]

    # Scope escalation rejection
    res = client.post(
        "/api/v1/auth/token",
        json={"grant_type": "api_key", "api_key": "cvai_dev_key_123", "requested_scopes": "super_admin_unauthorized"},
    )
    assert res.status_code == 400

    # Scope subset valid
    res = client.post(
        "/api/v1/auth/token",
        json={"grant_type": "api_key", "api_key": "cvai_dev_key_123", "requested_scopes": "review:read"},
    )
    assert res.status_code == 200

    # Refresh with non-refresh token (use access_token)
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": admin_token})
    assert res.status_code == 400

    # Refresh with expired token
    expired_token = create_jwt_token({"sub": "user", "type": "refresh"}, expires_delta_seconds=-10)
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": expired_token})
    assert res.status_code == 401

    # Refresh with tampered token
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": "not.a.valid.jwt"})
    assert res.status_code == 401


def test_jwt_manager_direct_edge_cases():
    import pytest

    from cerberus.core.jwt_auth import (
        InvalidTokenError,
        jwt_manager,
    )

    # Non-string or empty token
    with pytest.raises(InvalidTokenError):
        jwt_manager.decode_and_verify("")

    # Invalid dot count
    with pytest.raises(InvalidTokenError):
        jwt_manager.decode_and_verify("abc.def")

    # Malformed signature base64
    with pytest.raises(InvalidTokenError):
        jwt_manager.decode_and_verify("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.@@@invalid_base64@@@")

    # Token with future nbf claim
    import time

    future_nbf = int(time.time()) + 1000
    future_token = jwt_manager.create_token(subject="user", extra_claims={"nbf": future_nbf})
    with pytest.raises(InvalidTokenError):
        jwt_manager.decode_and_verify(future_token)
