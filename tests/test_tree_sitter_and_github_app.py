"""
Unit and Integration Tests for:
1. Tree-sitter AST Multi-Language Parity (TypeScript, Go, Rust, TSX)
2. Native GitHub App Webhook Listener for zero-click pull_request.opened reviews
"""

import json
import pytest
from fastapi.testclient import TestClient

from cerberus.api.app import app
from cerberus.config import settings
from cerberus.core.github_app import (
    parse_pull_request_event,
    build_pr_review_payload,
)
from cerberus.core.security import generate_webhook_signature
from cerberus.core.syntax_verifier import SyntaxVerifier, detect_language_from_path
from cerberus.models.schemas import (
    CodeReviewResponse,
    Finding,
    SeverityEnum,
    GitHubPullRequestInfo,
)

client = TestClient(app)


@pytest.mark.skipif(not SyntaxVerifier.is_tree_sitter_supported("typescript"), reason="tree-sitter typescript grammar not installed")
def test_tree_sitter_typescript_syntax():
    """Verify Tree-sitter TypeScript AST validation and error detection."""
    valid_ts = """
    interface UserConfig {
        id: string;
        roles: string[];
    }

    export class AuthService {
        private active: boolean = true;

        public authenticate(token: string): boolean {
            return token.length > 0 && this.active;
        }
    }
    """
    valid, err = SyntaxVerifier.verify(valid_ts, "typescript")
    assert valid is True
    assert err is None

    # Broken TypeScript code
    invalid_ts = "const token: string = ;"
    invalid, err = SyntaxVerifier.verify(invalid_ts, "typescript")
    assert invalid is False
    assert "SyntaxError" in err
    assert "line 1" in err


@pytest.mark.skipif(not SyntaxVerifier.is_tree_sitter_supported("tsx"), reason="tree-sitter tsx grammar not installed")
def test_tree_sitter_tsx_syntax():
    """Verify Tree-sitter TSX React JSX syntax validation."""
    valid_tsx = """
    import React from 'react';

    interface ButtonProps {
        label: string;
        onClick: () => void;
    }

    export const ActionButton: React.FC<ButtonProps> = ({ label, onClick }) => {
        return <button onClick={onClick} className="btn-primary">{label}</button>;
    };
    """
    valid, err = SyntaxVerifier.verify(valid_tsx, "tsx")
    assert valid is True
    assert err is None


@pytest.mark.skipif(not SyntaxVerifier.is_tree_sitter_supported("go"), reason="tree-sitter go grammar not installed")
def test_tree_sitter_go_syntax():
    """Verify Tree-sitter Go AST validation and error detection."""
    valid_go = r"""
    package main

    import (
        "fmt"
        "errors"
    )

    type Worker struct {
        ID int
    }

    func (w *Worker) Process() error {
        if w.ID <= 0 {
            return errors.New("invalid ID")
        }
        fmt.Printf("Worker %d processing\n", w.ID)
        return nil
    }
    """
    valid, err = SyntaxVerifier.verify(valid_go, "go")
    assert valid is True
    assert err is None

    # Broken Go code
    invalid_go = "package main\nfunc Broken("
    invalid, err = SyntaxVerifier.verify(invalid_go, "go")
    assert invalid is False
    assert "SyntaxError" in err


@pytest.mark.skipif(not SyntaxVerifier.is_tree_sitter_supported("rust"), reason="tree-sitter rust grammar not installed")
def test_tree_sitter_rust_syntax():
    """Verify Tree-sitter Rust AST validation and error detection."""
    valid_rs = """
    pub struct CacheConfig {
        pub capacity: usize,
        pub ttl_seconds: u64,
    }

    impl CacheConfig {
        pub fn new(capacity: usize) -> Self {
            Self {
                capacity,
                ttl_seconds: 3600,
            }
        }
    }
    """
    valid, err = SyntaxVerifier.verify(valid_rs, "rust")
    assert valid is True
    assert err is None

    # Broken Rust code
    invalid_rs = "pub fn broken( { let x = ; }"
    invalid, err = SyntaxVerifier.verify(invalid_rs, "rust")
    assert invalid is False
    assert "SyntaxError" in err


@pytest.mark.skipif(not SyntaxVerifier.is_tree_sitter_supported("typescript"), reason="tree-sitter not installed")
def test_ast_metadata_extraction():
    """Verify deep AST symbol extraction for TypeScript, Go, and Rust."""
    # TypeScript
    ts_code = """
    import { Router } from 'express';
    class Controller {}
    function handleRequest() {}
    """
    meta_ts = SyntaxVerifier.extract_ast_metadata(ts_code, "typescript")
    assert meta_ts["parser_type"] == "tree_sitter"
    assert "Controller" in meta_ts["classes_or_structs"]
    assert "handleRequest" in meta_ts["functions"]

    # Go
    go_code = """
    package engine
    import "sync"
    type Engine struct {}
    func NewEngine() *Engine { return &Engine{} }
    """
    meta_go = SyntaxVerifier.extract_ast_metadata(go_code, "go")
    assert meta_go["parser_type"] == "tree_sitter"
    assert "Engine" in meta_go["classes_or_structs"]
    assert "NewEngine" in meta_go["functions"]

    # Rust
    rs_code = """
    use std::sync::Arc;
    struct Guard {}
    fn lock_mutex() {}
    """
    meta_rs = SyntaxVerifier.extract_ast_metadata(rs_code, "rust")
    assert meta_rs["parser_type"] == "tree_sitter"
    assert "Guard" in meta_rs["classes_or_structs"]
    assert "lock_mutex" in meta_rs["functions"]


def test_github_app_parse_pull_request_event():
    """Verify parsing GitHub pull_request event payload."""
    payload = {
        "action": "opened",
        "number": 108,
        "pull_request": {
            "title": "Upgrade crypto auth",
            "body": "Replaces string comparison with timing-safe HMAC.",
            "head": {"sha": "c0ffee1234", "ref": "feat/timing-safe"},
            "base": {"ref": "main"},
            "diff_url": "https://github.com/org/repo/pull/108.diff",
            "html_url": "https://github.com/org/repo/pull/108"
        },
        "repository": {
            "name": "cerberus",
            "owner": {"login": "cerberus-ai"},
            "full_name": "cerberus-ai/cerberus"
        }
    }
    pr_info = parse_pull_request_event(payload)
    assert pr_info is not None
    assert pr_info.pr_number == 108
    assert pr_info.repo_owner == "cerberus-ai"
    assert pr_info.repo_name == "cerberus"
    assert pr_info.full_name == "cerberus-ai/cerberus"
    assert pr_info.head_sha == "c0ffee1234"
    assert pr_info.action == "opened"


def test_github_app_build_pr_review_payload():
    """Verify constructing official GitHub Pull Request Review payload."""
    pr_info = GitHubPullRequestInfo(
        action="opened",
        pr_number=55,
        repo_name="core",
        repo_owner="acme",
        full_name="acme/core",
        title="Sample PR",
        head_sha="headsha456"
    )
    mock_review = CodeReviewResponse(
        review_id="rev-gh-1",
        created_at="2026-11-14T12:00:00Z",
        status="completed",
        overall_score=85,
        findings_count=1,
        critical_issues=[],
        warnings=[
            Finding(
                category="Security",
                severity=SeverityEnum.HIGH,
                title="Timing Attack",
                message="Use hmac.compare_digest",
                line=12,
                recommendation="Replace =="
            )
        ],
        suggestions=[],
        unified_patch="--- a/auth.py\n+++ b/auth.py\n@@ -12,1 +12,1 @@\n-if a == b:\n+if timing_safe_compare(a, b):"
    )

    review_payload = build_pr_review_payload(mock_review, pr_info, filename="auth.py")
    assert review_payload.commit_id == "headsha456"
    assert review_payload.event == "APPROVE"
    assert "cerberus</> Autonomous Multi-Agent Code Review" in review_payload.body
    assert "85 / 100" in review_payload.body
    assert len(review_payload.comments) == 1
    assert review_payload.comments[0].path == "auth.py"
    assert review_payload.comments[0].line == 12


def test_github_webhook_pull_request_opened_flow():
    """Integration test: Zero-click pull_request.opened webhook flow."""
    secret = settings.SECRET_KEY
    payload_dict = {
        "action": "opened",
        "number": 77,
        "filename": "security.py",
        "code": "def auth_user(token):\n    return token == 'admin_secret'\n",
        "pull_request": {
            "title": "Add auth_user",
            "body": "Adds user authentication routine",
            "head": {"sha": "sha777", "ref": "feat-auth"},
            "base": {"ref": "main"}
        },
        "repository": {
            "name": "my-app",
            "owner": {"login": "corp"},
            "full_name": "corp/my-app"
        }
    }
    raw_payload = json.dumps(payload_dict).encode("utf-8")
    sig = generate_webhook_signature(raw_payload, secret)

    response = client.post(
        "/api/v1/review/webhooks/github",
        content=raw_payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": sig
        }
    )
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "completed"
    assert data["event"] == "pull_request"
    assert data["action"] == "opened"
    assert data["pr_number"] == 77
    assert data["repository"] == "corp/my-app"
    assert "overall_score" in data
    assert "pr_review_action" in data
    assert "github_review_payload" in data
    assert "body" in data["github_review_payload"]
    assert len(data["github_review_comments"]) > 0


def test_github_webhook_ping_event():
    """Verify GitHub webhook ping handshake event."""
    secret = settings.SECRET_KEY
    ping_payload = json.dumps({"zen": "Keep it logically awesome.", "hook_id": 9999}).encode("utf-8")
    sig = generate_webhook_signature(ping_payload, secret)

    response = client.post(
        "/api/v1/review/webhooks/github",
        content=ping_payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": sig
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pong"
    assert data["hook_id"] == 9999


def test_github_webhook_tamper_signature_rejection():
    """Verify tampered webhook payload is strictly rejected with 401."""
    secret = settings.SECRET_KEY
    valid_payload = json.dumps({"action": "opened"}).encode("utf-8")
    sig = generate_webhook_signature(valid_payload, secret)

    tampered_payload = json.dumps({"action": "opened", "malicious": True}).encode("utf-8")

    response = client.post(
        "/api/v1/review/webhooks/github",
        content=tampered_payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": sig  # Signature does not match tampered payload
        }
    )
    assert response.status_code == 401
    assert "Invalid GitHub X-Hub-Signature-256" in response.json()["detail"]
