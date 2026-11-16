# Contributing to Cerberus

Thank you for your interest in contributing to **Cerberus**! We welcome contributions ranging from bug fixes and new specialized code review agents to documentation improvements and test coverage.

Please take a few moments to review these guidelines before submitting a pull request.

---

## 🛠️ Development Setup

### 1. Prerequisites
- Python 3.11, 3.12, or 3.13+
- Git
- `pip` or `uv`
- (Optional) Docker & Docker Compose for containerized testing

### 2. Fork and Clone
```bash
git clone https://github.com/<your-username>/Cerberus-Code-Review.git
cd Cerberus-Code-Review
```

### 3. Create a Virtual Environment
```bash
python -m venv .venv
# On Linux/macOS:
source .venv/bin/activate
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
```

### 4. Install Dependencies & Pre-commit Hooks
```bash
pip install -e ".[dev]"
pre-commit install
```

### 5. Common Development Commands (via Makefile)
```bash
make help          # Show available commands
make check         # Run lint, typecheck, and security checks
make test-fast     # Run fast test suite
make test          # Run full test suite with coverage
make format        # Format code via ruff
```

### 6. Setup Environment Variables
```bash
cp .env.example .env
```
By default, `LLM_PROVIDER=heuristic` is active, allowing you to run all agents locally without external cloud credentials.

---

## 🌿 Branching Strategy

Create a branch with a descriptive prefix for your work:

- `feat/agent-kubernetes-manifests` (new features or agents)
- `fix/cvss-score-boundary` (bug fixes)
- `docs/clarify-watsonx-iam` (documentation changes)
- `perf/cache-invalidation-lru` (performance optimizations)
- `test/compliance-pci-dss` (additional test coverage)

```bash
git checkout -b feat/your-feature-name
```

---

## 🧪 Testing Guidelines

Before committing or pushing your changes, ensure that all unit and integration tests pass:

```bash
# Run the test suite
python -m pytest tests/ -q --tb=short

# Run specific agent tests
python -m pytest tests/test_agents.py
python -m pytest tests/test_compliance_agent.py
```

If you add new heuristics or agent rules, please write corresponding tests under the `tests/` directory to maintain high test coverage.

---

## 📐 Coding Standards

1. **Pythonic & Typed**: Code should adhere to PEP 8 standards with type hints (`typing` / Python 3.10+ union types `X | Y`).
2. **Logging Format**: Always use lazy `%s` formatting for logging (e.g. `logger.info("Starting %s", name)`). Never use f-strings in logger calls (Ruff rule `G` is strictly enforced).
3. **Docstrings**: Provide clear docstrings explaining agent heuristics, parameters, and return structures.
4. **Commit Messages**: Write meaningful, conventional commit messages:
   - `feat(agents): add Terraform IaC rule to Security Agent`
   - `fix(cli): correct exit code on lint failure`
   - `docs(readme): add docker compose quickstart badge`

---

## 📥 Submitting a Pull Request

1. Push your branch to your GitHub fork:
   ```bash
   git push origin feat/your-feature-name
   ```
2. Navigate to the upstream repository on GitHub and click **Compare & pull request**.
3. Fill out the Pull Request template:
   - Reference any related issues (e.g., `Closes #42`).
   - Describe what changed and why.
   - Confirm test results and manual verification.
4. Maintainers will review your PR and provide constructive feedback. Once approved, it will be merged!

---

## 💡 Questions or Ideas?

Feel free to open an issue or start a GitHub Discussion to discuss proposed features or architectural improvements before writing large amounts of code.
