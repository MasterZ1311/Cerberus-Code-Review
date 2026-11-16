# ADR-0001: Python AsyncIO & Event Loop Concurrency

## Status
**Accepted** (2026-01-15)

## Context
Cerberus coordinates multiple specialized code review agents simultaneously across multi-tenant API requests and webhook triggers. Analyzing a single pull request requires:
- Running 5–7 analysis agents (Security, Performance, Quality, Architecture, Compliance, Consensus, Fixer) in parallel.
- Calling external LLM APIs (OpenAI, Anthropic, Gemini, Groq) with network latencies ranging from 200ms to 5000ms.
- Querying Redis caches and writing findings to database storage.

Using synchronous multi-threading or multi-processing would result in high OS thread overhead, GIL contention, and memory bloat under high concurrent load.

## Decision
We adopted pure Python `asyncio` built on top of FastAPI and Uvicorn.
- Agents implement asynchronous interfaces (`async def analyze(...)`).
- Agent execution is multiplexed concurrently via `asyncio.gather()`.
- Non-blocking HTTP calls use `httpx.AsyncClient` with pooled persistent TCP connections.
- Non-blocking database calls use `SQLAlchemy` with `asyncpg` / `aiosqlite`.

## Consequences
### Positive
- Extremely low memory footprint (~50MB base per worker process).
- Capable of serving 10,000+ idle SSE connections and concurrent requests without OS thread exhaustion.
- Clear cancellation and timeout semantics via `asyncio.wait_for()`.

### Negative
- Any accidental blocking call (e.g. CPU-heavy regex or sync file I/O) can freeze the event loop. This is mitigated by delegating heavy parsing to background executor pools (`run_in_executor`).
