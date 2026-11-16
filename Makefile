# =========================================================================
# Cerberus Automation Makefile
# Unified Developer Workflow for Testing, Linting, Security, & Operations
# =========================================================================

.PHONY: help install pre-commit test test-fast test-cov lint format typecheck security lockfile clean serve dev docker-build

SHELL := /bin/bash
PYTHON ?= python

help:
	@echo "Available commands:"
	@echo "  make install       Install dependencies in editable development mode"
	@echo "  make pre-commit    Install and run pre-commit hooks on all files"
	@echo "  make test          Run full test suite with coverage report"
	@echo "  make test-fast     Run quick unit tests without slow benchmarks"
	@echo "  make lint          Check code style and linting via ruff"
	@echo "  make format        Format code using ruff"
	@echo "  make typecheck     Run static type checker (mypy)"
	@echo "  make security      Run bandit SAST and secret scanning"
	@echo "  make check         Run all quality gates: lint, typecheck, security"
	@echo "  make lockfile      Regenerate hashed requirements lockfiles"
	@echo "  make serve         Run local Cerberus API server via uvicorn"
	@echo "  make dev           Launch full stack with Redis via docker compose"
	@echo "  make clean         Remove build artifacts and pycache files"

install:
	$(PYTHON) -m pip install -e ".[dev]"
	pre-commit install

pre-commit:
	pre-commit run --all-files

test:
	pytest tests/ -v --cov=cerberus --cov-branch --cov-report=term-missing

test-fast:
	pytest tests/ -q -m "not slow"

test-cov:
	pytest tests/ --cov=cerberus --cov-branch --cov-report=html:htmlcov --cov-report=term-missing

lint:
	ruff check cerberus/ tests/

format:
	ruff format cerberus/ tests/

typecheck:
	mypy cerberus/ --strict

security:
	bandit -r cerberus/ -c pyproject.toml
	$(PYTHON) scripts/check_doc_secrets.py

check: lint typecheck security

lockfile:
	$(PYTHON) scripts/generate_lockfile.py --all

serve:
	uvicorn cerberus.api.app:create_app --factory --reload --host 127.0.0.1 --port 8000

dev:
	docker compose up --build

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov/ .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
