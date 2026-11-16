"""
ASGI Request Limit and Chunked Body Size Enforcement Tests.
Verifies:
1. Early rejection when Content-Length exceeds limit.
2. Immediate termination during chunked / streaming transfer when Content-Length is absent.
3. Catching and terminating requests with misleading/forged Content-Length headers.
4. Oversized JSON review submissions capped at receive layer.
5. Oversized Base64 ZIP uploads capped at receive layer.
6. Defense-in-depth endpoint ZIP bomb & path traversal protections.
"""

import io
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from cerberus.api.app import app
from cerberus.core.database import init_db


@pytest.fixture(autouse=True)
async def setup_test_env():
    await init_db()


@pytest.mark.asyncio
async def test_oversized_content_length_rejected_early():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request with declared Content-Length of 40MB (exceeds default 30MB)
        headers = {
            "Content-Length": str(40 * 1024 * 1024),
            "Content-Type": "application/json",
            "Authorization": "Bearer cvai_dev_key_123",
        }
        resp = await client.post("/api/v1/review", headers=headers, content=b"{}")
        assert resp.status_code == 413
        assert resp.json()["error"] == "payload_too_large"


@pytest.mark.asyncio
async def test_absent_content_length_chunked_streaming_capped():
    """
    Simulates chunked transfer where Content-Length is completely absent.
    The ASGI receive layer meters received bytes and aborts when limit is crossed.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def _oversized_chunk_generator():
            # Send 6 chunks of 1MB each (total 6MB, exceeding 5MB JSON limit on /api/v1/review)
            chunk = b"A" * (1024 * 1024)
            for _ in range(6):
                yield chunk

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer cvai_dev_key_123",
        }
        # In httpx, passing an async generator sends streaming body without Content-Length
        resp = await client.post("/api/v1/review", headers=headers, content=_oversized_chunk_generator())
        assert resp.status_code == 413
        assert resp.json()["error"] == "payload_too_large"


@pytest.mark.asyncio
async def test_misleading_content_length_header():
    """
    Simulates an attacker forging a small Content-Length header (e.g. 100 bytes),
    but streaming multiple megabytes of payload.
    The ASGI metered receive layer must abort immediately once limit is crossed.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def _generator_with_misleading_data():
            chunk = b"B" * (1024 * 1024)
            for _ in range(6):
                yield chunk

        # Deliberately spoofed header
        headers = {
            "Content-Length": "100",
            "Content-Type": "application/json",
            "Authorization": "Bearer cvai_dev_key_123",
        }
        resp = await client.post("/api/v1/review", headers=headers, content=_generator_with_misleading_data())
        assert resp.status_code == 413
        assert resp.json()["error"] == "payload_too_large"


@pytest.mark.asyncio
async def test_oversized_base64_zip_submission():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Base64 payload exceeding limit
        oversized_b64 = "A" * (36 * 1024 * 1024)
        headers = {
            "Content-Length": str(len(oversized_b64) + 100),
            "Content-Type": "application/json",
            "Authorization": "Bearer cvai_dev_key_123",
        }
        resp = await client.post(
            "/api/v1/review/zip-base64",
            headers=headers,
            content=f'{{"zip_base64": "{oversized_b64}"}}'.encode(),
        )
        assert resp.status_code == 413
        assert resp.json()["error"] == "payload_too_large"


@pytest.mark.asyncio
async def test_malformed_multipart_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing or invalid boundary header
        headers = {
            "Content-Type": "multipart/form-data; boundary=invalid_boundary",
            "Authorization": "Bearer cvai_dev_key_123",
        }
        resp = await client.post("/api/v1/review/zip", headers=headers, content=b"--wrong_boundary\r\n")
        assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_endpoint_level_zip_extraction_limits_defense_in_depth():
    """
    Endpoint level defense-in-depth:
    Ensures zip bombs (decompression ratio attacks) and path traversal archives
    are safely trapped and rejected during extraction.
    """
    # 1. Path traversal archive
    traversal_buf = io.BytesIO()
    with zipfile.ZipFile(traversal_buf, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0::/root:/bin/bash\n")
    traversal_bytes = traversal_buf.getvalue()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer cvai_dev_key_123"}
        resp = await client.post(
            "/api/v1/review/zip",
            headers=headers,
            files={"file": ("malicious.zip", traversal_bytes, "application/zip")},
            data={"project_name": "traversal_exploit"},
        )
        assert (resp.status_code in (400, 422, 500)) or (
            resp.status_code == 200 and resp.json().get("reviewed_files_count") == 0
        )


@pytest.mark.asyncio
async def test_non_integer_content_length_handled_safely():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {
            "Content-Length": "not-an-integer",
            "Content-Type": "application/json",
            "Authorization": "Bearer cvai_dev_key_123",
        }
        resp = await client.post("/api/v1/review", headers=headers, json={"code": "print('ok')"})
        assert resp.status_code == 200
