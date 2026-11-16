# ADR-0003: Offline Zero-Config AST Heuristic Engine as Default

## Status
**Accepted** (2026-02-15)

## Context
Many developer tools and security scanners require immediate cloud API keys (e.g. OpenAI, Anthropic) before a developer can test or run the CLI. This introduces severe onboarding friction, cost barriers, and breaks in CI pipelines where secrets cannot be shared across external forks.

## Decision
We engineered `HeuristicEngine` as the foundational, zero-config default engine:
- Operates 100% locally with zero internet access and zero API keys.
- Combines native Python AST (`ast.parse`) with multi-language Tree-sitter parsers and precision regex heuristics.
- Provides 125+ security, quality, performance, and compliance rules covering Python, TypeScript, Go, Rust, Java, C#, Ruby, and PHP.
- Produces deterministic, reproducible scores and CWE-annotated findings.

## Consequences
### Positive
- `pip install cerberus-ai && cerberus review file.py` works instantaneously on any machine.
- Air-gapped and high-security compliance environments can run reviews without sending code to cloud LLMs.
- Acts as a reliable fallback whenever cloud LLMs fail or trip circuit breakers.

### Negative
- Does not catch complex cross-file semantic business logic flaws that frontier LLMs can infer. Resolved by enabling cloud providers when keys are configured.
