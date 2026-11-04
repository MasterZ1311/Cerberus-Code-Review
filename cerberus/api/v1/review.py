"""
Code Review Endpoints: Single, Batch, Status, Results, Feedback, and WebSocket.
"""

import asyncio
import base64
import json
import logging
from pathlib import Path
import uuid
from collections import OrderedDict
from typing import Dict, List, Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from cerberus.agents.orchestrator import orchestrator
from cerberus.api.dependencies import validate_token_against_db, verify_api_key
from cerberus.config import settings
from cerberus.core.database import AsyncSessionLocal
from cerberus.models.database import CodeReviewRecord, FindingRecord, ReviewFeedbackRecord
from cerberus.models.schemas import (
    BatchReviewRequest,
    BatchReviewResponse,
    CodeReviewRequest,
    CodeReviewResponse,
    FeedbackRequest,
    FeedbackResponse,
    ReviewConfig,
    ZipBase64ReviewRequest,
    ZipReviewResponse,
)

logger = logging.getLogger("cerberus.api.review")
router = APIRouter(prefix="/api/v1/review", tags=["Review"])

# Bounded in-memory store for quick lookups and active WebSocket broadcasts
REVIEWS_STORE_MAX_ITEMS = getattr(settings, "CACHE_MAX_ITEMS", 1000)
reviews_store: OrderedDict[str, CodeReviewResponse] = OrderedDict()
zip_reviews_store: OrderedDict[str, ZipReviewResponse] = OrderedDict()
ws_connections: Dict[str, List[WebSocket]] = {}


def _store_review(review_id: str, response: CodeReviewResponse) -> None:
    """Store review in bounded OrderedDict with LRU eviction."""
    if review_id in reviews_store:
        reviews_store.move_to_end(review_id)
    else:
        while len(reviews_store) >= REVIEWS_STORE_MAX_ITEMS and reviews_store:
            reviews_store.popitem(last=False)
    reviews_store[review_id] = response


def _store_zip_review(review_id: str, response: ZipReviewResponse) -> None:
    """Store project zip review in bounded OrderedDict with LRU eviction."""
    if review_id in zip_reviews_store:
        zip_reviews_store.move_to_end(review_id)
    else:
        while len(zip_reviews_store) >= REVIEWS_STORE_MAX_ITEMS and zip_reviews_store:
            zip_reviews_store.popitem(last=False)
    zip_reviews_store[review_id] = response


@router.post("", response_model=CodeReviewResponse, status_code=status.HTTP_200_OK)
async def submit_review(
    request: CodeReviewRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Submit source code for multi-agent review across Security, Performance, and Quality.
    """
    if not request.code or not request.code.strip():
        raise HTTPException(status_code=400, detail="Source code snippet cannot be empty")

    response = await orchestrator.execute_review(request)
    _store_review(response.review_id, response)

    # Persist in background DB
    asyncio.create_task(_persist_review_record(request, response))

    # Notify connected WebSockets
    if response.review_id in ws_connections:
        active_sockets = list(ws_connections[response.review_id])
        for ws in active_sockets:
            try:
                await ws.send_text(json.dumps({
                    "event": "review_completed",
                    "review_id": response.review_id,
                    "overall_score": response.overall_score
                }))
            except Exception:
                if ws in ws_connections.get(response.review_id, []):
                    ws_connections[response.review_id].remove(ws)
        if response.review_id in ws_connections and not ws_connections[response.review_id]:
            del ws_connections[response.review_id]

    return response


@router.get("/{review_id}", response_model=CodeReviewResponse)
async def get_review_status(
    review_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get the current processing status and summary of a review."""
    if review_id in reviews_store:
        reviews_store.move_to_end(review_id)
        return reviews_store[review_id]

    # Check database fallback
    try:
        async with AsyncSessionLocal() as session:
            record = await session.get(CodeReviewRecord, review_id)
            if record and record.results_json:
                results_data = record.results_json
                if isinstance(results_data, str):
                    results_data = json.loads(results_data)
                if isinstance(results_data, dict):
                    response = CodeReviewResponse(**results_data)
                    _store_review(review_id, response)
                    return response
    except Exception as e:
        logger.warning(f"DB lookup failed for {review_id}: {e}")

    raise HTTPException(status_code=404, detail=f"Review with ID '{review_id}' was not found.")


@router.get("/{review_id}/results", response_model=CodeReviewResponse)
async def get_review_results(
    review_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Retrieve full synthesized results, agent findings, and remediation suggestions."""
    return await get_review_status(review_id, api_key)


@router.post("/batch", response_model=BatchReviewResponse)
async def batch_review(
    request: BatchReviewRequest,
    api_key: str = Depends(verify_api_key)
):
    """Submit multiple files or snippets for concurrent batch code review."""
    if len(request.files) > settings.MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size {len(request.files)} exceeds maximum allowed of {settings.MAX_BATCH_SIZE}"
        )

    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_BATCH_REVIEWS)

    async def _throttled_review(req):
        async with semaphore:
            return await orchestrator.execute_review(req)

    results: List[CodeReviewResponse] = await asyncio.gather(*[_throttled_review(req) for req in request.files])

    for res in results:
        _store_review(res.review_id, res)

    return BatchReviewResponse(
        batch_id=f"batch_{uuid.uuid4().hex[:12]}",
        total_files=len(results),
        reviews=results
    )


@router.post("/zip", response_model=ZipReviewResponse, status_code=status.HTTP_200_OK)
@router.post("/upload-zip", response_model=ZipReviewResponse, status_code=status.HTTP_200_OK)
async def upload_zip_review(
    file: UploadFile = File(..., description="ZIP archive containing source code"),
    project_name: Optional[str] = Form(None, description="Optional project name"),
    agents: Optional[str] = Form(None, description="Comma-separated agents to run"),
    blocking: bool = Form(False, description="Enable blocking mode"),
    api_key: str = Depends(verify_api_key)
):
    """
    Upload and review an entire project packaged as a .zip file.
    Extracts all supported source files and runs multi-agent reviews in parallel.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Uploaded file must have a .zip extension.")

    try:
        zip_bytes = await file.read()
        if not zip_bytes:
            raise HTTPException(status_code=400, detail="Uploaded ZIP file is empty.")

        agents_list = [a.strip() for a in agents.split(",") if a.strip()] if agents else None
        cfg = ReviewConfig(blocking_mode=blocking)
        p_name = project_name or Path(file.filename).stem

        response = await orchestrator.execute_zip_review(
            zip_source=zip_bytes,
            project_name=p_name,
            agents=agents_list,
            config=cfg
        )

        _store_zip_review(response.review_id, response)
        for fr in response.file_reviews:
            _store_review(fr.review_id, fr.review)

        return response
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception(f"Error processing ZIP review: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process ZIP review: {str(e)}")


@router.post("/zip-base64", response_model=ZipReviewResponse, status_code=status.HTTP_200_OK)
async def review_zip_base64(
    request: ZipBase64ReviewRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Review a project from base64-encoded ZIP data.
    Useful for automated CI/CD and direct JSON API integrations.
    """
    try:
        zip_bytes = base64.b64decode(request.zip_base64)
        if not zip_bytes:
            raise HTTPException(status_code=400, detail="Decoded ZIP content is empty.")

        cfg = ReviewConfig(blocking_mode=request.blocking or False)
        response = await orchestrator.execute_zip_review(
            zip_source=zip_bytes,
            project_name=request.project_name or "uploaded_project",
            agents=request.agents,
            config=cfg
        )

        _store_zip_review(response.review_id, response)
        for fr in response.file_reviews:
            _store_review(fr.review_id, fr.review)

        return response
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception(f"Error processing base64 ZIP review: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process base64 ZIP review: {str(e)}")


@router.get("/zip/{zip_review_id}", response_model=ZipReviewResponse)
async def get_zip_review(
    zip_review_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Retrieve full synthesized report of an uploaded project ZIP review."""
    if zip_review_id in zip_reviews_store:
        zip_reviews_store.move_to_end(zip_review_id)
        return zip_reviews_store[zip_review_id]
    raise HTTPException(status_code=404, detail=f"Project review '{zip_review_id}' was not found.")


@router.post("/{review_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    review_id: str,
    feedback: FeedbackRequest,
    api_key: str = Depends(verify_api_key)
):
    """Submit developer feedback and rating for a completed review."""
    try:
        async with AsyncSessionLocal() as session:
            record = ReviewFeedbackRecord(
                review_id=review_id,
                user_id=api_key,
                rating=feedback.rating,
                is_helpful=feedback.is_helpful,
                false_positives=feedback.false_positives,
                false_negatives=feedback.false_negatives,
                comments=feedback.comments
            )
            session.add(record)
            await session.commit()
    except Exception as e:
        logger.warning(f"Could not persist feedback: {e}")

    return FeedbackResponse(status="success", message="Feedback recorded. Thank you for improving Cerberus.")


@router.websocket("/{review_id}/ws")
async def websocket_review_stream(
    websocket: WebSocket,
    review_id: str,
    token: Optional[str] = Query(None)
):
    """Live WebSocket stream broadcasting agent lifecycle events and progress."""
    auth_header = websocket.headers.get("authorization")
    raw_token = token
    if not raw_token and auth_header and auth_header.startswith("Bearer "):
        raw_token = auth_header.split(" ", 1)[1].strip()

    is_valid = await validate_token_against_db(raw_token)
    if not is_valid:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or missing API key")
        return

    await websocket.accept()
    if review_id not in ws_connections:
        ws_connections[review_id] = []
    ws_connections[review_id].append(websocket)

    try:
        await websocket.send_text(json.dumps({
            "event": "connected",
            "review_id": review_id,
            "message": "Subscribed to live agent updates."
        }))
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if review_id in ws_connections:
            if websocket in ws_connections[review_id]:
                ws_connections[review_id].remove(websocket)
            if not ws_connections[review_id]:
                del ws_connections[review_id]


async def _persist_review_record(request: CodeReviewRequest, response: CodeReviewResponse) -> None:
    """Asynchronously persist review and findings to database."""
    try:
        async with AsyncSessionLocal() as session:
            review_rec = CodeReviewRecord(
                id=response.review_id,
                code_snippet=request.code[:2000],  # truncate if very large
                language=request.language or "python",
                status=response.status,
                overall_score=response.overall_score,
                processing_time_ms=response.processing_time_ms,
                results_json=response.model_dump(),
            )
            session.add(review_rec)

            # Add individual findings
            for f in response.critical_issues + response.warnings + response.suggestions:
                finding_rec = FindingRecord(
                    review_id=response.review_id,
                    agent_name=f.category,
                    severity=f.severity.value,
                    category=f.category,
                    title=f.title,
                    message=f.message,
                    line_number=f.line,
                    code_snippet=f.code_snippet,
                    remediation=f.recommendation,
                    suggestion=f.suggestion,
                    cwe_id=f.cwe_id,
                    cvss_score=f.cvss_score,
                )
                session.add(finding_rec)

            await session.commit()
    except Exception as e:
        logger.warning(f"Database background write error: {e}")
