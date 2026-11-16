# CodeVault AI - API Reference

**Version:** 0.1.0  
**Last Updated:** September 21, 2026  
**Base URL:** `http://localhost:8000` (local) or your deployed endpoint

---

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Rate Limiting](#rate-limiting)
- [Versioning](#versioning)
- [Core Endpoints](#core-endpoints)
  - [Submit Code Review](#submit-code-review)
  - [Get Review Status](#get-review-status)
  - [Get Review Results](#get-review-results)
  - [Batch Review Submission](#batch-review-submission)
  - [Submit Review Feedback](#submit-review-feedback)
  - [Live Review WebSocket Stream](#live-review-websocket-stream)
  - [Repository Analytics](#repository-analytics)
  - [List Available Agents](#list-available-agents)
  - [System Configuration](#system-configuration)
  - [Health Check & Readiness Probe](#health-check--readiness-probe)
- [Webhooks](#webhooks)
- [SDK Examples](#sdk-examples)
- [Common Integration Patterns](#common-integration-patterns)
- [Error Handling](#error-handling)
- [Response Formats](#response-formats)

---

## Overview

The CodeVault AI REST API provides programmatic access to the multi-agent code review system. All endpoints return JSON responses and follow RESTful conventions.

**Key Features:**
- RESTful design with predictable resource URLs
- JSON request/response bodies
- Standard HTTP status codes
- API key authentication
- Rate limiting and quotas
- Async review processing with webhooks
- Idempotent operations where applicable

**API Characteristics:**
- **Protocol**: HTTPS (HTTP for local development)
- **Content-Type**: `application/json`
- **Character Encoding**: UTF-8
- **Response Format**: JSON
- **Date Format**: ISO 8601 (e.g., `2026-09-21T10:30:00Z`)

---

## Authentication

CodeVault AI uses API key authentication for all non-health check endpoints.

### Obtaining an API Key

**Local Development:**
In local development mode (`ENVIRONMENT=development`), the default API key `cvai_dev_key_123` is automatically seeded and ready for immediate use.

You can also create a new API key using the CLI:
```bash
python -m cerberus.cli create-api-key --name "my-dev-key"

# Output:
# API Key created successfully!
# Key: cvai_1234567890abcdefghijklmnop
# Name: my-dev-key
```

**Production Deployment:**
```bash
# Using the CLI
python -m cerberus.cli create-api-key --name "production-key"
```

### Using API Keys

Include the API key in the `Authorization` header with the `Bearer` scheme:

```bash
curl -H "Authorization: Bearer cvai_dev_key_123" \
     http://localhost:8000/api/v1/review
```

**Authentication Errors:**

| Status Code | Error Code | Description |
|-------------|------------|-------------|
| 401 | `missing_authentication` | No Authorization header provided |
| 401 | `invalid_api_key` | API key is invalid or expired |
| 403 | `insufficient_permissions` | API key lacks required permissions |

---

## Rate Limiting

Rate limits protect the API from abuse and ensure fair usage.

**Default Limits:**
- **Anonymous**: 10 requests per hour
- **Authenticated**: 100 requests per hour per API key
- **Pro Tier**: 1,000 requests per hour
- **Enterprise**: Custom limits

**Rate Limit Headers:**
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1695384600
```

**Rate Limit Exceeded Response:**
```json
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Rate limit exceeded. Try again in 3600 seconds.",
    "retry_after": 3600
  }
}
```

**HTTP Status**: `429 Too Many Requests`

---

## Versioning

The API uses URL-based versioning: `/api/v1/`, `/api/v2/`, etc.

**Current Version**: `v1`

**Version Support Policy:**
- Current version: Fully supported
- Previous version: Supported for 12 months after new version release
- Deprecated version: 6-month sunset period with warnings

**Version-Specific Headers:**
```http
X-API-Version: 1.0.0
X-API-Deprecated: false
```

---

## Core Endpoints

### Submit Code Review

Submit code for multi-agent review.

**Endpoint:** `POST /api/v1/review`

**Request Headers:**
```http
Authorization: Bearer cvai_your_api_key
Content-Type: application/json
```

**Request Body:**
```json
{
  "code": "def calculate_total(items):\n    total = 0\n    for item in items:\n        total += item['price']\n    return total",
  "language": "python",
  "filename": "calculator.py",
  "context": {
    "project_name": "shopping-cart",
    "git_commit": "abc123",
    "file_path": "src/utils/calculator.py"
  },
  "agents": ["security", "performance", "quality"],
  "config": {
    "severity_threshold": "medium",
    "blocking_mode": true
  }
}
```

**Request Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string | Yes | The source code to review (max 100KB) |
| `language` | string | No | Programming language (auto-detected if omitted) |
| `filename` | string | No | Original filename for context |
| `context` | object | No | Additional context (project name, git info, etc.) |
| `agents` | array | No | List of agents to run (default: all) |
| `config` | object | No | Review-specific configuration overrides |

**Example 1: Basic Python Review**
```bash
curl -X POST http://localhost:8000/api/v1/review \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "import os\n\nAPI_KEY = \"sk-1234567890\"\n\ndef get_user(user_id):\n    query = \"SELECT * FROM users WHERE id = \" + user_id\n    return db.execute(query)",
    "language": "python",
    "filename": "api.py"
  }'
```

**Response (201 Created):**
```json
{
  "review_id": "rev_8f7e6d5c4b3a2918",
  "status": "processing",
  "created_at": "2026-09-21T10:30:00Z",
  "estimated_completion": "2026-09-21T10:30:15Z",
  "agents_scheduled": ["security", "performance", "quality"],
  "webhook_url": null,
  "_links": {
    "self": "/api/v1/review/rev_8f7e6d5c4b3a2918",
    "results": "/api/v1/review/rev_8f7e6d5c4b3a2918/results"
  }
}
```

**Example 2: JavaScript/TypeScript Review**
```bash
curl -X POST http://localhost:8000/api/v1/review \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "function fetchUserData(userId) {\n  return fetch(`https://api.example.com/users/${userId}`)\n    .then(res => res.json())\n    .catch(err => console.log(err))\n}",
    "language": "javascript",
    "filename": "userService.js",
    "agents": ["security", "quality"]
  }'
```

**Response (201 Created):**
```json
{
  "review_id": "rev_9a8b7c6d5e4f3021",
  "status": "processing",
  "created_at": "2026-09-21T10:35:00Z",
  "estimated_completion": "2026-09-21T10:35:12Z",
  "agents_scheduled": ["security", "quality"],
  "webhook_url": null,
  "_links": {
    "self": "/api/v1/review/rev_9a8b7c6d5e4f3021",
    "results": "/api/v1/review/rev_9a8b7c6d5e4f3021/results"
  }
}
```

**Example 3: Review with Webhook Notification**
```bash
curl -X POST http://localhost:8000/api/v1/review \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "SELECT * FROM users WHERE email = '\'' + userInput + '\'';",
    "language": "sql",
    "filename": "queries.sql",
    "webhook_url": "https://myapp.com/webhooks/codevault",
    "webhook_secret": "whsec_your_webhook_secret"
  }'
```

**Response (201 Created):**
```json
{
  "review_id": "rev_7f6e5d4c3b2a1908",
  "status": "processing",
  "created_at": "2026-09-21T10:40:00Z",
  "estimated_completion": "2026-09-21T10:40:10Z",
  "agents_scheduled": ["security", "performance", "quality"],
  "webhook_url": "https://myapp.com/webhooks/codevault",
  "_links": {
    "self": "/api/v1/review/rev_7f6e5d4c3b2a1908",
    "results": "/api/v1/review/rev_7f6e5d4c3b2a1908/results"
  }
}
```

**Example 4: Cached Review (Fast Response)**
```bash
curl -X POST http://localhost:8000/api/v1/review \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def hello():\n    print(\"Hello, World!\")",
    "language": "python"
  }'
```

**Response (200 OK - Cached):**
```json
{
  "review_id": "rev_6e5d4c3b2a190817",
  "status": "completed",
  "created_at": "2026-09-21T10:45:00Z",
  "completed_at": "2026-09-21T10:45:00Z",
  "cache_hit": true,
  "results": {
    "overall_score": 95,
    "severity_summary": {
      "critical": 0,
      "high": 0,
      "medium": 0,
      "low": 1,
      "info": 2
    },
    "agents": [
      {
        "name": "security",
        "status": "completed",
        "score": 100,
        "findings": []
      },
      {
        "name": "performance",
        "status": "completed",
        "score": 95,
        "findings": [
          {
            "severity": "low",
            "title": "Consider using f-strings",
            "message": "For better performance and readability, consider using f-strings instead of concatenation",
            "line": 2,
            "suggestion": "print(f\"Hello, World!\")"
          }
        ]
      },
      {
        "name": "quality",
        "status": "completed",
        "score": 90,
        "findings": [
          {
            "severity": "info",
            "title": "Add docstring",
            "message": "Consider adding a docstring to describe the function's purpose",
            "line": 1,
            "suggestion": "def hello():\n    \"\"\"Print a greeting message.\"\"\"\n    print(\"Hello, World!\")"
          }
        ]
      }
    ]
  },
  "_links": {
    "self": "/api/v1/review/rev_6e5d4c3b2a190817"
  }
}
```

**Example 5: Blocking Review with Severity Threshold**
```bash
curl -X POST http://localhost:8000/api/v1/review \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "password = request.GET.get(\"password\")\nuser = authenticate(username, password)",
    "language": "python",
    "filename": "auth.py",
    "config": {
      "severity_threshold": "medium",
      "blocking_mode": true
    }
  }'
```

**Response (200 OK):**
```json
{
  "review_id": "rev_5d4c3b2a19081726",
  "status": "completed",
  "created_at": "2026-09-21T10:50:00Z",
  "completed_at": "2026-09-21T10:50:08Z",
  "blocking": true,
  "should_block": true,
  "block_reason": "Found 1 critical and 1 high severity issues",
  "results": {
    "overall_score": 35,
    "severity_summary": {
      "critical": 1,
      "high": 1,
      "medium": 0,
      "low": 0,
      "info": 0
    },
    "agents": [
      {
        "name": "security",
        "status": "completed",
        "score": 30,
        "execution_time_ms": 3450,
        "findings": [
          {
            "id": "SEC-001",
            "severity": "critical",
            "category": "authentication",
            "title": "Credentials exposed in GET request",
            "message": "Password is transmitted via GET parameter, which is logged in server logs and browser history. This is a critical security vulnerability.",
            "line": 1,
            "column": 11,
            "code_snippet": "password = request.GET.get(\"password\")",
            "explanation": "GET parameters are logged by web servers, proxies, and browsers. Passwords should only be sent via POST in request body or headers.",
            "recommendation": "Use POST request with password in request body. Consider using HTTPS and proper authentication tokens.",
            "references": [
              "https://owasp.org/www-project-top-ten/2017/A2_2017-Broken_Authentication",
              "https://cwe.mitre.org/data/definitions/598.html"
            ],
            "suggested_fix": "# Use POST instead\npassword = request.POST.get(\"password\")\n# Better: Use token-based auth\ntoken = request.headers.get(\"Authorization\")"
          },
          {
            "id": "SEC-002",
            "severity": "high",
            "category": "input_validation",
            "title": "Unvalidated user input",
            "message": "User input is passed directly to authentication without validation",
            "line": 2,
            "column": 7,
            "code_snippet": "user = authenticate(username, password)",
            "explanation": "Always validate and sanitize user input before using it in authentication operations.",
            "recommendation": "Add input validation: check length, allowed characters, implement rate limiting",
            "suggested_fix": "if not username or len(username) > 255:\n    raise ValueError(\"Invalid username\")\nif not password or len(password) < 8:\n    raise ValueError(\"Invalid password\")\nuser = authenticate(username, password)"
          }
        ]
      }
    ]
  },
  "_links": {
    "self": "/api/v1/review/rev_5d4c3b2a19081726"
  }
}
```

**Status Codes:**

| Code | Meaning | When |
|------|---------|------|
| 201 | Created | Review successfully created and processing |
| 200 | OK | Review completed immediately (cache hit) |
| 400 | Bad Request | Invalid request body or parameters |
| 401 | Unauthorized | Missing or invalid API key |
| 413 | Payload Too Large | Code exceeds size limit (100KB) |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error during review processing |
| 503 | Service Unavailable | LLM provider unavailable |

---

### Get Review Status

Retrieve the current status and results of a review.

**Endpoint:** `GET /api/v1/review/{review_id}`

**Request Headers:**
```http
Authorization: Bearer cvai_your_api_key
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `review_id` | string | The unique review identifier (e.g., `rev_abc123`) |

**Example 1: Get In-Progress Review**
```bash
curl -X GET http://localhost:8000/api/v1/review/rev_8f7e6d5c4b3a2918 \
  -H "Authorization: Bearer cvai_dev_key_123"
```

**Response (200 OK):**
```json
{
  "review_id": "rev_8f7e6d5c4b3a2918",
  "status": "processing",
  "created_at": "2026-09-21T10:30:00Z",
  "progress": {
    "total_agents": 3,
    "completed_agents": 2,
    "current_agent": "quality",
    "percent_complete": 66
  },
  "agents_status": [
    {
      "name": "security",
      "status": "completed",
      "execution_time_ms": 3200
    },
    {
      "name": "performance",
      "status": "completed",
      "execution_time_ms": 2800
    },
    {
      "name": "quality",
      "status": "processing",
      "started_at": "2026-09-21T10:30:06Z"
    }
  ],
  "_links": {
    "self": "/api/v1/review/rev_8f7e6d5c4b3a2918"
  }
}
```

**Example 2: Get Completed Review**
```bash
curl -X GET http://localhost:8000/api/v1/review/rev_9a8b7c6d5e4f3021 \
  -H "Authorization: Bearer cvai_dev_key_123"
```

**Response (200 OK):**
```json
{
  "review_id": "rev_9a8b7c6d5e4f3021",
  "status": "completed",
  "created_at": "2026-09-21T10:35:00Z",
  "completed_at": "2026-09-21T10:35:11Z",
  "duration_ms": 11240,
  "cache_hit": false,
  "results": {
    "overall_score": 72,
    "severity_summary": {
      "critical": 0,
      "high": 1,
      "medium": 3,
      "low": 5,
      "info": 2
    },
    "blocking": false,
    "agents": [
      {
        "name": "security",
        "status": "completed",
        "score": 65,
        "execution_time_ms": 4100,
        "token_usage": {
          "prompt_tokens": 1250,
          "completion_tokens": 380,
          "total_tokens": 1630
        },
        "findings_count": 4,
        "findings": [
          {
            "id": "SEC-101",
            "severity": "high",
            "category": "error_handling",
            "title": "Error messages expose sensitive information",
            "message": "Catch block logs full error details which may expose system information",
            "line": 5,
            "code_snippet": ".catch(err => console.log(err))",
            "recommendation": "Log errors securely without exposing details to users",
            "suggested_fix": ".catch(err => {\n  logger.error(err);\n  return { error: 'An error occurred' };\n})"
          }
        ]
      },
      {
        "name": "quality",
        "status": "completed",
        "score": 78,
        "execution_time_ms": 3800,
        "token_usage": {
          "prompt_tokens": 1180,
          "completion_tokens": 420,
          "total_tokens": 1600
        },
        "findings_count": 6,
        "findings": [
          {
            "id": "QUA-201",
            "severity": "medium",
            "category": "error_handling",
            "title": "Insufficient error handling",
            "message": "Promise rejection is logged but not properly handled",
            "line": 5,
            "recommendation": "Return a user-friendly error or propagate for upstream handling"
          }
        ]
      }
    ],
    "metadata": {
      "language": "javascript",
      "filename": "userService.js",
      "file_size_bytes": 234,
      "lines_of_code": 6
    }
  },
  "_links": {
    "self": "/api/v1/review/rev_9a8b7c6d5e4f3021",
    "download_json": "/api/v1/review/rev_9a8b7c6d5e4f3021/export?format=json",
    "download_markdown": "/api/v1/review/rev_9a8b7c6d5e4f3021/export?format=markdown",
    "download_sarif": "/api/v1/review/rev_9a8b7c6d5e4f3021/export?format=sarif"
  }
}
```

**Example 3: Get Failed Review**
```bash
curl -X GET http://localhost:8000/api/v1/review/rev_failed_123 \
  -H "Authorization: Bearer cvai_dev_key_123"
```

**Response (200 OK):**
```json
{
  "review_id": "rev_failed_123",
  "status": "failed",
  "created_at": "2026-09-21T10:40:00Z",
  "failed_at": "2026-09-21T10:40:05Z",
  "error": {
    "code": "llm_provider_error",
    "message": "OpenAI API rate limit exceeded",
    "details": "Rate limit reached for requests",
    "retry_after": 60
  },
  "agents_status": [
    {
      "name": "security",
      "status": "completed",
      "execution_time_ms": 3100
    },
    {
      "name": "performance",
      "status": "failed",
      "error": "LLM provider rate limit exceeded"
    },
    {
      "name": "quality",
      "status": "cancelled"
    }
  ],
  "_links": {
    "self": "/api/v1/review/rev_failed_123",
    "retry": "/api/v1/review/rev_failed_123/retry"
  }
}
```

**Example 4: Get Review with Query Parameters**
```bash
curl -X GET "http://localhost:8000/api/v1/review/rev_9a8b7c6d5e4f3021?include=findings&severity=high,critical" \
  -H "Authorization: Bearer cvai_dev_key_123"
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `include` | string | Comma-separated fields to include (e.g., `findings,metadata`) |
| `severity` | string | Filter findings by severity (e.g., `high,critical`) |
| `format` | string | Response format: `json` (default), `markdown`, `sarif` |

**Example 5: Poll for Completion**
```bash
# Poll every 2 seconds until complete
while true; do
  STATUS=$(curl -s -H "Authorization: Bearer cvai_dev_key_123" \
    http://localhost:8000/api/v1/review/rev_8f7e6d5c4b3a2918 | jq -r '.status')
  
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    echo "Review $STATUS"
    break
  fi
  
  echo "Status: $STATUS... polling again in 2s"
  sleep 2
done
```

**Status Codes:**

| Code | Meaning |
|------|---------|
| 200 | OK - Review found |
| 401 | Unauthorized |
| 404 | Not Found - Review ID doesn't exist |
| 429 | Too Many Requests |

---

### Get Review Results

Retrieve full synthesized review results, agent findings, security vulnerabilities, and remediation recommendations.

**Endpoint:** `GET /api/v1/review/{review_id}/results`

**Request Headers:**
```http
Authorization: Bearer cvai_dev_key_123
```

**Example:**
```bash
curl -X GET http://localhost:8000/api/v1/review/rev_8f7e6d5c4b3a2918/results \
  -H "Authorization: Bearer cvai_dev_key_123"
```

**Response (200 OK):**
```json
{
  "review_id": "rev_8f7e6d5c4b3a2918",
  "status": "completed",
  "created_at": "2026-10-10T10:30:00Z",
  "completed_at": "2026-10-10T10:30:02Z",
  "cache_hit": false,
  "blocking": false,
  "should_block": false,
  "overall_score": 85.0,
  "processing_time_ms": 1420,
  "critical_issues": [],
  "warnings": [
    {
      "id": "SEC-002",
      "severity": "high",
      "category": "security",
      "title": "Hardcoded API Secret Detected",
      "message": "Potential API credential embedded in source file.",
      "line": 3,
      "cwe_id": "CWE-798",
      "cvss_score": 7.5,
      "recommendation": "Migrate credential to environment variable or secret manager."
    }
  ],
  "suggestions": [
    {
      "id": "QUAL-001",
      "severity": "medium",
      "category": "quality",
      "title": "Missing Function Docstring",
      "message": "Function calculate_total lacks a docstring description.",
      "line": 1,
      "recommendation": "Add a descriptive docstring following PEP 257."
    }
  ],
  "agents_scheduled": ["security", "performance", "quality", "architecture", "compliance"]
}
```

---

### Batch Review Submission

Submit multiple files for review in a single request.

**Endpoint:** `POST /api/v1/review/batch`

**Request Headers:**
```http
Authorization: Bearer cvai_your_api_key
Content-Type: application/json
```

**Request Body:**
```json
{
  "files": [
    {
      "filename": "api.py",
      "language": "python",
      "code": "import os\n\nAPI_KEY = os.getenv('API_KEY')\n\ndef get_data():\n    pass"
    },
    {
      "filename": "utils.js",
      "language": "javascript",
      "code": "function formatDate(date) {\n  return date.toString();\n}"
    }
  ],
  "context": {
    "project_name": "my-project",
    "git_commit": "abc123"
  },
  "config": {
    "parallel_processing": true,
    "agents": ["security", "quality"]
  }
}
```

**Example 1: Batch Review Multiple Files**
```bash
curl -X POST http://localhost:8000/api/v1/review/batch \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "filename": "auth.py",
        "code": "def login(username, password):\n    if username == \"admin\" and password == \"admin\":\n        return True\n    return False"
      },
      {
        "filename": "database.py",
        "code": "def execute_query(user_input):\n    query = \"SELECT * FROM users WHERE name = '\'' + user_input + '\'';\"\n    return db.execute(query)"
      }
    ],
    "config": {
      "agents": ["security"],
      "severity_threshold": "high"
    }
  }'
```

**Response (201 Created):**
```json
{
  "batch_id": "batch_7f6e5d4c3b2a",
  "status": "processing",
  "created_at": "2026-09-21T11:00:00Z",
  "total_files": 2,
  "reviews": [
    {
      "review_id": "rev_auth_py_001",
      "filename": "auth.py",
      "status": "processing",
      "_links": {
        "self": "/api/v1/review/rev_auth_py_001"
      }
    },
    {
      "review_id": "rev_database_py_002",
      "filename": "database.py",
      "status": "processing",
      "_links": {
        "self": "/api/v1/review/rev_database_py_002"
      }
    }
  ],
  "_links": {
    "self": "/api/v1/review/batch/batch_7f6e5d4c3b2a",
    "status": "/api/v1/review/batch/batch_7f6e5d4c3b2a/status"
  }
}
```

**Example 2: Check Batch Status**
```bash
curl -X GET http://localhost:8000/api/v1/review/batch/batch_7f6e5d4c3b2a/status \
  -H "Authorization: Bearer cvai_dev_key_123"
```

**Response (200 OK):**
```json
{
  "batch_id": "batch_7f6e5d4c3b2a",
  "status": "completed",
  "created_at": "2026-09-21T11:00:00Z",
  "completed_at": "2026-09-21T11:00:18Z",
  "duration_ms": 18450,
  "total_files": 2,
  "summary": {
    "completed": 2,
    "failed": 0,
    "total_findings": 8,
    "critical_findings": 2,
    "high_findings": 3,
    "medium_findings": 2,
    "low_findings": 1
  },
  "reviews": [
    {
      "review_id": "rev_auth_py_001",
      "filename": "auth.py",
      "status": "completed",
      "score": 25,
      "findings_count": 3,
      "severity_summary": {
        "critical": 1,
        "high": 2,
        "medium": 0,
        "low": 0
      },
      "_links": {
        "self": "/api/v1/review/rev_auth_py_001"
      }
    },
    {
      "review_id": "rev_database_py_002",
      "filename": "database.py",
      "status": "completed",
      "score": 15,
      "findings_count": 5,
      "severity_summary": {
        "critical": 1,
        "high": 1,
        "medium": 2,
        "low": 1
      },
      "_links": {
        "self": "/api/v1/review/rev_database_py_002"
      }
    }
  ],
  "_links": {
    "self": "/api/v1/review/batch/batch_7f6e5d4c3b2a/status",
    "download_report": "/api/v1/review/batch/batch_7f6e5d4c3b2a/export"
  }
}
```

**Status Codes:**

| Code | Meaning |
|------|---------|
| 201 | Created - Batch review started |
| 400 | Bad Request - Invalid file data |
| 401 | Unauthorized |
| 413 | Payload Too Large - Too many files or total size exceeded |
| 429 | Too Many Requests |

---

### Submit Review Feedback

Submit developer feedback and accuracy ratings for a completed review.

**Endpoint:** `POST /api/v1/review/{review_id}/feedback`

**Request Headers:**
```http
Authorization: Bearer cvai_dev_key_123
Content-Type: application/json
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `review_id` | string | Unique review identifier |

**Request Body:**
```json
{
  "rating": 5,
  "is_helpful": true,
  "false_positives": 0,
  "false_negatives": 0,
  "comments": "Accurately flagged OWASP Top 10 vulnerabilities and suggested idiomatic fixes."
}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Feedback recorded. Thank you for improving Cerberus."
}
```

---

### Live Review WebSocket Stream

Subscribe to real-time agent execution events and completion broadcasts over WebSockets.

**Endpoint:** `ws://localhost:8000/api/v1/review/{review_id}/ws?token=cvai_dev_key_123`

**Connection Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `review_id` | string | Yes | The ID of the review being tracked |
| `token` | string | Yes (in query or header) | API key token (e.g. `cvai_dev_key_123`) |

**Authentication:**
Provide the token via query parameter (`?token=cvai_dev_key_123`) or via handshake header (`Authorization: Bearer cvai_dev_key_123`). Invalid or missing tokens result in closure with code `1008` (Policy Violation).

**Example (JavaScript / Node.js):**
```javascript
const WebSocket = require('ws');

const reviewId = 'rev_8f7e6d5c4b3a2918';
const ws = new WebSocket(`ws://localhost:8000/api/v1/review/${reviewId}/ws?token=cvai_dev_key_123`);

ws.on('open', () => {
  console.log('Connected to Cerberus review stream');
});

ws.on('message', (data) => {
  const event = JSON.parse(data);
  console.log('Received event:', event);
});
```

**Event Messages:**

*On Connection:*
```json
{
  "event": "connected",
  "review_id": "rev_8f7e6d5c4b3a2918",
  "message": "Subscribed to live agent updates."
}
```

*On Review Completion:*
```json
{
  "event": "review_completed",
  "review_id": "rev_8f7e6d5c4b3a2918",
  "overall_score": 88.5
}
```

---

### Repository Analytics

Retrieve historical review performance metrics and quality trajectories for a repository.

**Endpoint:** `GET /api/v1/analytics/repositories/{owner}/{repo}`

**Request Headers:**
```http
Authorization: Bearer cvai_dev_key_123
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `owner` | string | Repository owner or organization |
| `repo` | string | Repository name |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `from_date` | string | No | Optional starting timestamp filter (ISO 8601) |
| `to_date` | string | No | Optional ending timestamp filter (ISO 8601) |

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/analytics/repositories/cerberus-org/core-service" \
  -H "Authorization: Bearer cvai_dev_key_123"
```

**Response (200 OK):**
```json
{
  "repository": "cerberus-org/core-service",
  "metrics": {
    "total_reviews": 128,
    "avg_score": 88.5,
    "vulnerabilities_prevented": 34,
    "security_trend": "+18.2%",
    "technical_debt_trajectory": "-12.5%",
    "performance_optimizations": 42
  }
}
```

---

### List Available Agents

Get information about available review agents and their capabilities.

**Endpoint:** `GET /api/v1/agents`

**Request Headers:**
```http
Authorization: Bearer cvai_dev_key_123
```

**Example:**
```bash
curl -X GET http://localhost:8000/api/v1/agents \
  -H "Authorization: Bearer cvai_dev_key_123"
```

**Response (200 OK):**
```json
[
  {
    "id": "security",
    "name": "security",
    "version": "1.2.0",
    "purpose": "Identify security vulnerabilities, secrets leakage, injection flaws, and CVSS risks",
    "capabilities": [
      "SQL Injection Detection (CWE-89)",
      "Command Injection (CWE-78)",
      "Hardcoded Credentials & API Secrets (CWE-798)",
      "Weak Cryptographic Algorithms (CWE-328)",
      "Insecure Object Deserialization (CWE-502)",
      "CVSS 3.1 Severity Scoring",
      "OWASP Top 10 Threat Analysis",
      "Exploitability Probability Estimation"
    ],
    "status": "active"
  },
  {
    "id": "performance",
    "name": "performance",
    "version": "1.1.0",
    "purpose": "Detect algorithmic bottlenecks, O(n²) loops, N+1 queries, and memory inefficiencies",
    "capabilities": [
      "Algorithmic Complexity Analysis (Big-O)",
      "Nested Iteration Detection (O(n²))",
      "Database N+1 Query Antipatterns",
      "String Concatenation Memory Leaks",
      "Caching Opportunity Identification",
      "Estimated Latency Improvement Calculations"
    ],
    "status": "active"
  },
  {
    "id": "quality",
    "name": "quality",
    "version": "1.1.0",
    "purpose": "Evaluate readability, maintainability, docstring coverage, and clean coding standards",
    "capabilities": [
      "Docstring Completeness & API Documentation",
      "Cognitive & Cyclomatic Complexity",
      "Long Method & Monolith Detection",
      "Dangerous Bare Except Clauses",
      "Wildcard Import Pollution",
      "Refactoring & Clean Code Suggestions"
    ],
    "status": "active"
  },
  {
    "id": "architecture",
    "name": "architecture",
    "version": "1.0.0",
    "purpose": "Validate system architecture, module coupling, and structural anti-patterns",
    "capabilities": [
      "Deep Coupling & Relative Import Detection",
      "Cyclic Dependency Risk Analysis",
      "Single Responsibility Principle (SRP) Verification",
      "Architectural Modularity Scoring"
    ],
    "status": "active"
  },
  {
    "id": "compliance",
    "name": "compliance",
    "version": "2.0.0",
    "purpose": "Audit code against HIPAA, GDPR, SOC 2, PCI-DSS, and CCPA regulatory mandates",
    "capabilities": [
      "HIPAA Security Rule (45 CFR §164.312 - ePHI, In-Transit TLS, Audit Logging)",
      "GDPR Data Protection (Articles 5, 6, 17, 25, 32 - Minimization, Consent, Erasure)",
      "SOC 2 Trust Services Criteria (CC6.1, CC6.6, CC7.1, CC7.2 - Secrets, RBAC, Masking)",
      "PCI-DSS v4.0 (Req 3.2, 3.4, 3.5 - PAN Luhn Validation, CVV Storage Prohibition)",
      "CCPA / CPRA (§1798.105, §1798.120 - Do-Not-Sell Opt-Out, DSAR Verification)",
      "Automated Regulatory Remediation Timelines & SLA Generation",
      "Multi-Framework Individual Compliance Scoring Matrix"
    ],
    "status": "active"
  }
]
```

---

### System Configuration

Retrieve or update active runtime configuration parameters.

#### Get Current Configuration

**Endpoint:** `GET /api/v1/config`

**Request Headers:**
```http
Authorization: Bearer cvai_dev_key_123
```

**Example:**
```bash
curl -X GET http://localhost:8000/api/v1/config \
  -H "Authorization: Bearer cvai_dev_key_123"
```

**Response (200 OK):**
```json
{
  "environment": "development",
  "llm_provider": "heuristic",
  "enabled_agents": [
    "security",
    "performance",
    "quality",
    "architecture",
    "compliance"
  ],
  "cache_enabled": true,
  "cache_ttl_seconds": 86400,
  "severity_threshold": "medium",
  "blocking_mode": false,
  "rate_limit_per_hour": 100
}
```

#### Update Configuration

**Endpoint:** `PUT /api/v1/config`

**Request Headers:**
```http
Authorization: Bearer cvai_dev_key_123
Content-Type: application/json
```

**Request Body:**
```json
{
  "enabled_agents": "security,performance,quality,architecture,compliance",
  "severity_threshold": "high",
  "blocking_mode": true
}
```

**Example:**
```bash
curl -X PUT http://localhost:8000/api/v1/config \
  -H "Authorization: Bearer cvai_dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled_agents": "security,performance,quality",
    "severity_threshold": "high",
    "blocking_mode": true
  }'
```

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Configuration updated successfully"
}
```

---

### Health Check & Readiness Probe

Inspect service liveness, uptime, database connectivity, cache status, and routing readiness.

#### Liveness Health Check

**Endpoint:** `GET /api/v1/health` (also accessible at `GET /health`)

**No Authentication Required**

**Example:**
```bash
curl -X GET http://localhost:8000/api/v1/health
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2026-10-10T12:00:00.000000+00:00",
  "database": "connected",
  "cache": "redis",
  "active_agents": [
    "security",
    "performance",
    "quality",
    "architecture",
    "compliance"
  ],
  "uptime_seconds": 128.45
}
```

#### Readiness Probe

**Endpoint:** `GET /api/v1/ready` (also accessible at `GET /ready`)

**No Authentication Required**

**Example:**
```bash
curl -X GET http://localhost:8000/api/v1/ready
```

**Response (200 OK):**
```json
{
  "status": "ready"
}
```

---

## Webhooks

Configure webhooks to receive notifications when reviews complete.

### Webhook Configuration

Include webhook URL when submitting a review:

```json
{
  "code": "...",
  "webhook_url": "https://myapp.com/webhooks/codevault",
  "webhook_secret": "whsec_your_secret_key"
}
```

### Webhook Payload

When a review completes, CodeVault AI sends a POST request:

**Webhook Request:**
```http
POST /webhooks/codevault HTTP/1.1
Host: myapp.com
Content-Type: application/json
X-CodeVault-Signature: sha256=abc123...
X-CodeVault-Event: review.completed

{
  "event": "review.completed",
  "timestamp": "2026-09-21T11:25:00Z",
  "review_id": "rev_8f7e6d5c4b3a2918",
  "status": "completed",
  "data": {
    "overall_score": 85,
    "severity_summary": {
      "critical": 0,
      "high": 1,
      "medium": 2,
      "low": 3,
      "info": 1
    },
    "agents_completed": ["security", "performance", "quality"],
    "duration_ms": 12450
  },
  "_links": {
    "review": "http://localhost:8000/api/v1/review/rev_8f7e6d5c4b3a2918"
  }
}
```

### Verifying Webhook Signatures

**Python Example:**
```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected_sig = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected_sig}", signature)

# Usage
from flask import Flask, request

app = Flask(__name__)

@app.route('/webhooks/codevault', methods=['POST'])
def handle_webhook():
    signature = request.headers.get('X-CodeVault-Signature')
    secret = '${WEBHOOK_SECRET}'
    
    if not verify_webhook(request.data, signature, secret):
        return 'Invalid signature', 401
    
    event = request.json
    # Process event...
    return 'OK', 200
```

**Node.js Example:**
```javascript
const crypto = require('crypto');

function verifyWebhook(payload, signature, secret) {
  const expectedSig = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(`sha256=${expectedSig}`)
  );
}

// Express.js usage
app.post('/webhooks/codevault', express.raw({type: 'application/json'}), (req, res) => {
  const signature = req.headers['x-codevault-signature'];
  const secret = '${WEBHOOK_SECRET}';
  
  if (!verifyWebhook(req.body, signature, secret)) {
    return res.status(401).send('Invalid signature');
  }
  
  const event = JSON.parse(req.body);
  // Process event...
  res.send('OK');
});
```

### Webhook Events

| Event | Description |
|-------|-------------|
| `review.created` | Review was created and queued |
| `review.processing` | Review processing has started |
| `review.completed` | Review completed successfully |
| `review.failed` | Review failed |
| `batch.completed` | Batch review completed |

---

## SDK Examples

### Python SDK

```python
from codevault import CodeVault

# Initialize client
client = CodeVault(api_key="${CERBERUS_API_KEY}")

# Submit review
review = client.review(
    code="""
    def login(username, password):
        if username == "admin" and password == "admin":
            return True
        return False
    """,
    language="python",
    agents=["security", "quality"]
)

# Wait for completion
result = review.wait()

# Check results
if result.should_block:
    print(f"❌ Review failed with score {result.overall_score}/100")
    for finding in result.critical_findings:
        print(f"  - {finding.title}")
else:
    print(f"✅ Review passed with score {result.overall_score}/100")

# Async usage
async def review_code():
    async with CodeVault(api_key="cvai_key") as client:
        review = await client.review_async(code="...", language="python")
        result = await review.wait_async()
        return result
```

### JavaScript/TypeScript SDK

```javascript
import { CodeVault } from '@codevault/sdk';

// Initialize client
const client = new CodeVault({ apiKey: '${CERBERUS_API_KEY}' });

// Submit review
const review = await client.review({
  code: `
    function login(username, password) {
      if (username === "admin" && password === "admin") {
        return true;
      }
      return false;
    }
  `,
  language: 'javascript',
  agents: ['security', 'quality']
});

// Wait for completion
const result = await review.wait();

// Check results
if (result.shouldBlock) {
  console.log(`❌ Review failed with score ${result.overallScore}/100`);
  result.criticalFindings.forEach(finding => {
    console.log(`  - ${finding.title}`);
  });
} else {
  console.log(`✅ Review passed with score ${result.overallScore}/100`);
}

// Stream progress
review.on('progress', (progress) => {
  console.log(`Progress: ${progress.percentComplete}%`);
});

review.on('completed', (result) => {
  console.log('Review completed!', result);
});
```

---

## Common Integration Patterns

### CI/CD Integration (GitHub Actions)

```yaml
name: Code Review
on: [pull_request]

jobs:
  codevault-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run CodeVault AI Review
        env:
          CODEVAULT_API_KEY: ${{ secrets.CODEVAULT_API_KEY }}
        run: |
          # Get changed files
          git diff --name-only origin/main...HEAD > changed_files.txt
          
          # Review each file
          while read file; do
            if [ -f "$file" ]; then
              curl -X POST http://localhost:8000/api/v1/review \
                -H "Authorization: Bearer $CODEVAULT_API_KEY" \
                -H "Content-Type: application/json" \
                -d @- << EOF
          {
            "code": "$(cat $file | jq -Rs .)",
            "filename": "$file",
            "context": {
              "pr_number": "${{ github.event.pull_request.number }}",
              "commit": "${{ github.sha }}"
            }
          }
          EOF
            fi
          done < changed_files.txt
```

### Pre-commit Hook Integration

```bash
#!/bin/bash
# .git/hooks/pre-commit

CODEVAULT_API_KEY="${CERBERUS_API_KEY}"
API_URL="http://localhost:8000/api/v1/review"

# Get staged files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM)

for FILE in $STAGED_FILES; do
  # Skip if not a code file
  if [[ ! $FILE =~ \.(py|js|ts|java|go|rb)$ ]]; then
    continue
  fi
  
  echo "Reviewing $FILE..."
  
  # Submit for review
  CODE=$(cat "$FILE" | jq -Rs .)
  RESPONSE=$(curl -s -X POST "$API_URL" \
    -H "Authorization: Bearer $CODEVAULT_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"code\": $CODE, \"filename\": \"$FILE\", \"config\": {\"blocking_mode\": true}}")
  
  # Check if blocking
  SHOULD_BLOCK=$(echo "$RESPONSE" | jq -r '.should_block // false')
  
  if [ "$SHOULD_BLOCK" = "true" ]; then
    echo "❌ Review failed for $FILE"
    echo "$RESPONSE" | jq '.results.agents[].findings[] | "  - [\(.severity)] \(.title)"'
    echo ""
    echo "Commit blocked due to critical issues. Fix them or use 'git commit --no-verify' to bypass."
    exit 1
  fi
done

echo "✅ All files passed review"
exit 0
```

---

## Error Handling

### Error Response Format

All errors follow a consistent format:

```json
{
  "error": {
    "code": "error_code_here",
    "message": "Human-readable error message",
    "details": "Additional context about the error",
    "field": "field_name",
    "documentation_url": "https://docs.codevault.ai/errors/error_code_here"
  },
  "request_id": "req_abc123",
  "timestamp": "2026-09-21T11:30:00Z"
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `missing_authentication` | 401 | No API key provided |
| `invalid_api_key` | 401 | API key is invalid or expired |
| `insufficient_permissions` | 403 | API key lacks required permissions |
| `rate_limit_exceeded` | 429 | Too many requests |
| `invalid_request_body` | 400 | Malformed JSON or missing required fields |
| `code_too_large` | 413 | Code exceeds size limit |
| `invalid_language` | 400 | Unsupported programming language |
| `agent_not_found` | 404 | Specified agent doesn't exist |
| `review_not_found` | 404 | Review ID doesn't exist |
| `llm_provider_error` | 503 | LLM provider is unavailable |
| `database_error` | 500 | Database operation failed |
| `internal_error` | 500 | Unexpected server error |

### Retry Logic

Implement exponential backoff for retries:

```python
import time
import requests

def review_with_retry(code, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "http://localhost:8000/api/v1/review",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={"code": code}
            )
            
            if response.status_code == 429:
                # Rate limited - wait and retry
                retry_after = int(response.headers.get('Retry-After', 60))
                time.sleep(retry_after)
                continue
            
            if response.status_code >= 500:
                # Server error - exponential backoff
                wait_time = (2 ** attempt) + random.random()
                time.sleep(wait_time)
                continue
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
    
    raise Exception("Max retries exceeded")
```

---

## Response Formats

### JSON (Default)

Standard JSON response format (shown in all examples above).

### Markdown

**Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/review/rev_abc123/export?format=markdown" \
  -H "Authorization: Bearer cvai_dev_key_123"
```

**Response:**
```markdown
# Code Review Report

**Review ID:** rev_abc123  
**Status:** Completed  
**Score:** 72/100  
**Date:** 2026-09-21 11:35:00 UTC

## Summary

- **Critical Issues:** 0
- **High Issues:** 1
- **Medium Issues:** 3
- **Low Issues:** 5
- **Info:** 2

## Security Agent (Score: 65/100)

### 🔴 HIGH - Error messages expose sensitive information

**Line 5:** `.catch(err => console.log(err))`

Catch block logs full error details which may expose system information.

**Recommendation:** Log errors securely without exposing details to users

**Suggested Fix:**
```javascript
.catch(err => {
  logger.error(err);
  return { error: 'An error occurred' };
})
```

---
```

### SARIF (Static Analysis Results Interchange Format)

**Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/review/rev_abc123/export?format=sarif" \
  -H "Authorization: Bearer cvai_dev_key_123"
```

**Response:**
```json
{
  "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [
    {
      "tool": {
        "driver": {
          "name": "CodeVault AI",
          "version": "0.1.0",
          "informationUri": "https://codevault.ai"
        }
      },
      "results": [
        {
          "ruleId": "SEC-101",
          "level": "error",
          "message": {
            "text": "Error messages expose sensitive information"
          },
          "locations": [
            {
              "physicalLocation": {
                "artifactLocation": {
                  "uri": "userService.js"
                },
                "region": {
                  "startLine": 5
                }
              }
            }
          ]
        }
      ]
    }
  ]
}
```

---

## Next Steps

- **[Agent Specifications](03-agent-specifications.md)** - Learn about each agent's capabilities
- **[Configuration Reference](05-configuration-reference.md)** - Customize API behavior
- **[Installation Guide](04-installation-setup.md)** - Set up your own instance

---

**API Version:** 0.1.0  
**Documentation Version:** 1.0  
**Last Updated:** September 21, 2026

*For support, visit [docs.codevault.ai](https://docs.codevault.ai) or open an issue on [GitHub](https://github.com/codevault-ai/codevault/issues)*
