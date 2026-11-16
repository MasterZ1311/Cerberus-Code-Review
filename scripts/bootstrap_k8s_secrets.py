#!/usr/bin/env python3
"""
Kubernetes Secrets Bootstrapper for Cerberus.
Generates cryptographically secure production secrets and creates
the required 'cerberus-secrets' Kubernetes Secret manifest.
"""

import argparse
import secrets
import sys
from pathlib import Path
from typing import Optional


def generate_secrets_manifest(
    secret_key: Optional[str] = None,
    db_password: Optional[str] = None,
    github_webhook_secret: Optional[str] = None,
    openai_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
    db_host: str = "cerberus-postgres.cerberus.svc.cluster.local",
    db_port: int = 5432,
    db_user: str = "cerberus",
    db_name: str = "cerberus_db",
) -> str:
    """Generate Kubernetes Secret YAML with cryptographically secure random defaults."""
    sec_key = secret_key or secrets.token_hex(32)
    db_pass = db_password or secrets.token_urlsafe(24)
    gh_sec = github_webhook_secret or secrets.token_hex(20)

    db_url = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    manifest = f"""apiVersion: v1
kind: Secret
metadata:
  name: cerberus-secrets
  namespace: cerberus
  labels:
    app.kubernetes.io/name: cerberus-api
    app.kubernetes.io/part-of: cerberus-system
    app.kubernetes.io/managed-by: cerberus-bootstrap
type: Opaque
stringData:
  SECRET_KEY: "{sec_key}"
  DATABASE_URL: "{db_url}"
  GITHUB_WEBHOOK_SECRET: "{gh_sec}"
  OPENAI_API_KEY: "{openai_key or ""}"
  ANTHROPIC_API_KEY: "{anthropic_key or ""}"
  GEMINI_API_KEY: ""
  GROQ_API_KEY: ""
  DEEPSEEK_API_KEY: ""
"""
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Kubernetes secrets for Cerberus")
    parser.add_argument(
        "--output",
        "-o",
        default="k8s/secrets.yaml",
        help="Target output file path for generated secrets manifest",
    )
    parser.add_argument("--stdout", action="store_true", help="Print manifest to stdout instead of writing to file")
    parser.add_argument("--secret-key", help="Explicit SECRET_KEY override (min 32 chars)")
    parser.add_argument("--db-password", help="Explicit database password override")
    parser.add_argument("--github-secret", help="Explicit GitHub webhook HMAC secret")
    args = parser.parse_args()

    if args.secret_key and len(args.secret_key) < 32:
        print("Error: SECRET_KEY must be at least 32 characters for security.", file=sys.stderr)
        return 1

    manifest = generate_secrets_manifest(
        secret_key=args.secret_key,
        db_password=args.db_password,
        github_webhook_secret=args.github_secret,
    )

    if args.stdout:
        print(manifest)
        return 0

    out_path = Path(args.output).resolve()
    out_path.write_text(manifest, encoding="utf-8")
    print(f"Successfully generated Kubernetes secrets manifest at: {out_path}")
    print("WARNING: Keep this file secure and never commit it to source control.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
